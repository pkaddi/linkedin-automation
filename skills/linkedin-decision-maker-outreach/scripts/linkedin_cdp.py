#!/usr/bin/env python3
"""Send sealed LinkedIn messages through a user-managed Chrome CDP session."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, Protocol
from urllib.parse import urljoin, urlsplit

import outreach_tracker as tracker


DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_SELECTORS = Path(__file__).resolve().parents[1] / "references" / "linkedin-selectors.json"
REQUIRED_SELECTOR_GROUPS = {
    "signed_in",
    "signed_out",
    "account_warning",
    "messaging_root",
    "profile_identity",
    "message_button",
    "composer",
    "composer_recipient",
    "send_button",
    "outgoing_message",
    "conversation_link",
}


class CdpError(RuntimeError):
    """A fail-closed CDP or LinkedIn UI error."""


class DeliveryUncertain(CdpError):
    """Send may have happened, so automatic retry is forbidden."""


def normalized_text(value: str) -> str:
    return " ".join((value or "").split())


def recipient_matches(expected: str, shown: str) -> bool:
    expected_name = normalized_text(expected).casefold()
    shown_name = normalized_text(shown).casefold()
    return shown_name == expected_name or shown_name.startswith(expected_name + " ")


def validate_cdp_url(value: str, allow_remote: bool = False) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https", "ws", "wss"} or not parts.hostname:
        raise CdpError("CDP URL must be an http(s) or ws(s) endpoint.")
    if not allow_remote and parts.hostname.lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise CdpError("Remote CDP endpoints are disabled. Use --allow-remote-cdp explicitly.")
    return value


def load_selectors(path: Path) -> dict[str, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CdpError(f"Cannot load selector file {path}: {exc}") from exc
    selectors = document.get("selectors") if isinstance(document, dict) else None
    version = document.get("version") if isinstance(document, dict) else None
    if not isinstance(version, str) or not version:
        raise CdpError("Selector file has no version.")
    if not isinstance(selectors, dict):
        raise CdpError("Selector file has no selectors object.")
    missing = sorted(REQUIRED_SELECTOR_GROUPS - selectors.keys())
    invalid = sorted(
        key for key, values in selectors.items()
        if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values)
    )
    if missing or invalid:
        details = []
        if missing:
            details.append("missing groups: " + ", ".join(missing))
        if invalid:
            details.append("invalid groups: " + ", ".join(invalid))
        raise CdpError("Invalid selector file: " + "; ".join(details))
    return selectors


class BrowserSession(Protocol):
    def preflight(self) -> dict[str, str]: ...
    def prepare_message(self, recipient: str, profile_url: str, message: str) -> None: ...
    def click_send(self) -> None: ...
    def verify_delivery(self, message: str) -> tuple[str, str]: ...


class PlaywrightChromeSession:
    """A thin browser adapter; tracker state deliberately lives elsewhere."""

    def __init__(self, cdp_url: str, selectors: dict[str, list[str]], timeout_ms: int = 15_000):
        self.cdp_url = cdp_url
        self.selectors = selectors
        self.timeout_ms = timeout_ms
        self._playwright = None
        self.browser = None
        self.page = None
        self._outgoing_before: list[str] = []

    def __enter__(self) -> "PlaywrightChromeSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CdpError(
                "Playwright is required. Install it with: python3 -m pip install 'playwright>=1.55,<2'"
            ) from exc
        try:
            self._playwright = sync_playwright().start()
            self.browser = self._playwright.chromium.connect_over_cdp(
                self.cdp_url, timeout=self.timeout_ms
            )
            if not self.browser.contexts:
                raise CdpError("Chrome exposed no browser context through CDP.")
            self.page = self.browser.contexts[0].new_page()
            self.page.set_default_timeout(self.timeout_ms)
            return self
        except CdpError:
            self.__exit__(None, None, None)
            raise
        except Exception as exc:
            self.__exit__(None, None, None)
            raise CdpError(f"Could not attach to Chrome CDP at {self.cdp_url}: {exc}") from exc

    def __exit__(self, *_: object) -> None:
        if self.page is not None:
            try:
                self.page.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

    def _locator(self, group: str, *, visible: bool = True, timeout_ms: int | None = None):
        assert self.page is not None
        timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        deadline = time.monotonic() + timeout / 1000
        while True:
            for selector in self.selectors[group]:
                locator = self.page.locator(selector)
                try:
                    count = locator.count()
                    for index in range(count - 1, -1, -1):
                        candidate = locator.nth(index)
                        if not visible or candidate.is_visible():
                            return candidate, selector
                except Exception:
                    continue
            if time.monotonic() >= deadline:
                break
            self.page.wait_for_timeout(100)
        raise CdpError(f"LinkedIn control not found for selector group: {group}")

    def _has(self, group: str) -> bool:
        try:
            self._locator(group, timeout_ms=0)
            return True
        except CdpError:
            return False

    def _assert_no_warning(self) -> None:
        assert self.page is not None
        url = self.page.url.lower()
        if "checkpoint" in url or "challenge" in url or self._has("account_warning"):
            raise CdpError("LinkedIn displayed an account warning or checkpoint. Stop and review it manually.")

    def preflight(self) -> dict[str, str]:
        assert self.page is not None and self.browser is not None
        try:
            self.page.goto("https://www.linkedin.com/messaging/", wait_until="domcontentloaded")
            self._assert_no_warning()
            if "/login" in self.page.url.lower() or self._has("signed_out"):
                raise CdpError("LinkedIn is signed out in the attached Chrome profile.")
            self._locator("signed_in")
            self._locator("messaging_root")
            return {
                "chrome_version": self.browser.version,
                "linkedin": "signed_in",
                "messaging": "available",
            }
        except CdpError:
            raise
        except Exception as exc:
            raise CdpError(f"LinkedIn preflight failed: {exc}") from exc

    def prepare_message(self, recipient: str, profile_url: str, message: str) -> None:
        assert self.page is not None
        try:
            self.page.goto(profile_url, wait_until="domcontentloaded")
            self._assert_no_warning()
            if "/login" in self.page.url.lower() or self._has("signed_out"):
                raise CdpError("LinkedIn signed out before the message could be prepared.")
            expected_path = urlsplit(profile_url).path.rstrip("/").casefold()
            actual_path = urlsplit(self.page.url).path.rstrip("/").casefold()
            if actual_path != expected_path:
                raise CdpError(
                    f"Profile URL mismatch: expected {expected_path!r}, LinkedIn opened {actual_path!r}."
                )
            identity, _ = self._locator("profile_identity")
            shown_name = normalized_text(identity.inner_text())
            if not recipient_matches(recipient, shown_name):
                raise CdpError(f"Recipient mismatch: expected {recipient!r}, LinkedIn showed {shown_name!r}.")
            button, _ = self._locator("message_button")
            button.click()
            composer, _ = self._locator("composer")
            header, _ = self._locator("composer_recipient")
            shown_recipient = normalized_text(header.inner_text())
            if not recipient_matches(recipient, shown_recipient):
                raise CdpError(
                    f"Composer recipient mismatch: expected {recipient!r}, showed {shown_recipient!r}."
                )
            existing = normalized_text(composer.inner_text())
            if existing and existing != normalized_text(message):
                raise CdpError("Composer contains unexpected text; nothing was sent.")
            if not existing:
                composer.fill(message)
            entered = normalized_text(composer.inner_text())
            if entered != normalized_text(message):
                raise CdpError("Composer text does not exactly match the sealed message.")
            self._locator("send_button")
            self._outgoing_before = self._outgoing_texts()
        except CdpError:
            raise
        except Exception as exc:
            raise CdpError(f"Could not prepare the LinkedIn message: {exc}") from exc

    def click_send(self) -> None:
        try:
            button, _ = self._locator("send_button")
            button.click()
        except Exception as exc:
            raise DeliveryUncertain(f"Send click did not complete cleanly: {exc}") from exc

    def verify_delivery(self, message: str) -> tuple[str, str]:
        assert self.page is not None
        expected = normalized_text(message)
        try:
            deadline = time.monotonic() + self.timeout_ms / 1000
            while time.monotonic() < deadline:
                texts = self._outgoing_texts()
                if texts.count(expected) > self._outgoing_before.count(expected):
                    url = self.page.url
                    if "/messaging/" not in url:
                        try:
                            link, _ = self._locator("conversation_link", timeout_ms=500)
                            href = link.get_attribute("href")
                            url = urljoin("https://www.linkedin.com", href) if href else url
                        except CdpError:
                            pass
                    proof = f"Visible outgoing message matched sha256:{tracker.sha256_text(message)}"
                    return url, proof
                self.page.wait_for_timeout(100)
        except Exception as exc:
            raise DeliveryUncertain(f"Could not verify the outgoing message: {exc}") from exc
        raise DeliveryUncertain("The exact message was not visible as a new outgoing message.")

    def _outgoing_texts(self) -> list[str]:
        assert self.page is not None
        texts: list[str] = []
        for selector in self.selectors["outgoing_message"]:
            locator = self.page.locator(selector)
            try:
                for index in range(locator.count()):
                    value = normalized_text(locator.nth(index).inner_text())
                    if value:
                        texts.append(value)
            except Exception:
                continue
        return texts


def _call_tracker(handler, **values):
    return handler(SimpleNamespace(**values))


@contextmanager
def dispatch_lock(tracker_path: Path) -> Iterator[None]:
    lock_path = tracker_path.with_suffix(tracker_path.suffix + ".cdp.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
    except FileExistsError as exc:
        raise CdpError(f"Another dispatch may be active: {lock_path}") from exc
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def dispatch(tracker_path: Path, session: BrowserSession, limit: int) -> dict[str, object]:
    if not 1 <= limit <= 5:
        raise CdpError("Dispatch limit must be between 1 and 5.")
    preflight = session.preflight()
    ready = _call_tracker(
        tracker.command_ready, tracker=tracker_path, record_id=None, limit=limit
    )["ready"]
    results: list[dict[str, str]] = []
    for candidate in ready:
        record_id = candidate["record_id"]
        expected_sha = candidate["approved_payload_sha256"]
        try:
            current = _call_tracker(
                tracker.command_ready,
                tracker=tracker_path,
                record_id=record_id,
                limit=1,
            )["ready"][0]
            if current != candidate:
                raise CdpError("Tracker payload changed after the dispatch queue was read.")
            session.prepare_message(
                current["full_name"], current["profile_url"], current["draft_message"]
            )
            current = _call_tracker(
                tracker.command_ready,
                tracker=tracker_path,
                record_id=record_id,
                limit=1,
            )["ready"][0]
            if current["approved_payload_sha256"] != expected_sha:
                raise CdpError("Approved payload changed immediately before Send.")
            attempt_id = str(uuid.uuid4())
            _call_tracker(
                tracker.command_begin_send,
                tracker=tracker_path,
                record_id=record_id,
                expected_payload_sha=expected_sha,
                attempt_id=attempt_id,
            )
            try:
                session.click_send()
                conversation_url, proof = session.verify_delivery(current["draft_message"])
            except Exception as exc:
                _call_tracker(
                    tracker.command_mark_failed,
                    tracker=tracker_path,
                    record_id=record_id,
                    error=str(exc),
                    safe_to_retry=False,
                )
                results.append({"record_id": record_id, "send_status": "manual_review", "error": str(exc)})
                break
            sent = _call_tracker(
                tracker.command_mark_sent,
                tracker=tracker_path,
                record_id=record_id,
                expected_payload_sha=expected_sha,
                conversation_url=conversation_url,
                delivery_proof=proof,
            )
            results.append({"record_id": record_id, "send_status": str(sent["send_status"])})
        except (CdpError, tracker.TrackerError) as exc:
            results.append({"record_id": record_id, "send_status": "ready", "error": str(exc)})
            break
    return {"preflight": preflight, "attempted": len(results), "results": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selectors", type=Path, default=DEFAULT_SELECTORS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight", help="Check Chrome and LinkedIn without composing.")
    preflight.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    preflight.add_argument("--allow-remote-cdp", action="store_true")
    dispatch_parser = subparsers.add_parser("dispatch", help="Send sealed rows through Chrome CDP.")
    dispatch_parser.add_argument("--tracker", type=Path, required=True)
    dispatch_parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    dispatch_parser.add_argument("--limit", type=int, default=5)
    dispatch_parser.add_argument("--confirm-send", action="store_true")
    dispatch_parser.add_argument("--allow-remote-cdp", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cdp_url = validate_cdp_url(args.cdp_url, args.allow_remote_cdp)
        selectors = load_selectors(args.selectors)
        if args.command == "dispatch" and not args.confirm_send:
            raise CdpError("Dispatch requires --confirm-send before it may click Send.")
        with PlaywrightChromeSession(cdp_url, selectors) as session:
            if args.command == "preflight":
                result = session.preflight()
            else:
                with dispatch_lock(args.tracker):
                    result = dispatch(args.tracker, session, args.limit)
    except (CdpError, tracker.TrackerError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
