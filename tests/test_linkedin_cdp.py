from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "linkedin-decision-maker-outreach"
SCRIPT_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("linkedin_cdp", SCRIPT_DIR / "linkedin_cdp.py")
assert SPEC and SPEC.loader
CDP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CDP)
TRACKER = CDP.tracker


def write_tracker(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACKER.FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle))


def ready_tracker(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    path = tmp_path / "outreach.csv"
    row = {field: "" for field in TRACKER.FIELDS}
    row.update(
        {
            "schema_version": TRACKER.SCHEMA_VERSION,
            "record_id": "record-1",
            "first_name": "Asha",
            "last_name": "Rao",
            "full_name": "Asha Rao",
            "title": "Head of Operations",
            "company": "Acme",
            "profile_url": "https://linkedin.com/in/asha-rao",
            "offer_sha256": "offer",
            "role_match": "yes",
            "matched_role": "Head of Operations",
            "role_reason": "Title match",
            "research_status": "complete",
            "research_summary": "Acme is hiring operations analysts.",
            "research_sources": "https://acme.example/careers",
            "personalization_hook": "Operations hiring",
            "draft_message": "Hi Asha, I saw Acme is expanding operations. Would a short comparison help?",
            "approval_status": "approved",
            "approved_at": TRACKER.now_iso(),
            "send_status": "ready",
            "updated_at": TRACKER.now_iso(),
        }
    )
    row["draft_message_sha256"] = TRACKER.message_sha(row)
    row["approved_message_sha256"] = TRACKER.message_sha(row)
    row["approved_payload_sha256"] = TRACKER.payload_sha(row)
    write_tracker(path, [row])
    return path, row


class FakeSession:
    def __init__(self, failure: str = ""):
        self.failure = failure
        self.prepared: list[tuple[str, str, str]] = []

    def preflight(self):
        if self.failure == "signed_out":
            raise CDP.CdpError("LinkedIn is signed out")
        return {"chrome_version": "Chrome/140", "linkedin": "signed_in", "messaging": "available"}

    def prepare_message(self, recipient: str, profile_url: str, message: str):
        if self.failure in {"recipient", "text", "selector"}:
            raise CDP.CdpError(self.failure + " mismatch")
        self.prepared.append((recipient, profile_url, message))

    def click_send(self):
        if self.failure == "click":
            raise CDP.DeliveryUncertain("click result unknown")

    def verify_delivery(self, message: str):
        if self.failure == "verify":
            raise CDP.DeliveryUncertain("exact outgoing message not visible")
        return "https://www.linkedin.com/messaging/thread/abc", "visible exact message hash"


def test_dispatch_records_verified_send(tmp_path: Path) -> None:
    path, original = ready_tracker(tmp_path)
    result = CDP.dispatch(path, FakeSession(), 1)
    row = read_row(path)
    assert result["results"] == [{"record_id": "record-1", "send_status": "sent"}]
    assert row["send_status"] == "sent"
    assert row["approved_payload_sha256"] == original["approved_payload_sha256"]
    assert row["send_attempt_id"]
    assert row["conversation_url"].endswith("/thread/abc")
    assert row["delivery_verified_at"]
    assert row["delivery_proof"] == "visible exact message hash"


@pytest.mark.parametrize("failure", ["recipient", "text", "selector"])
def test_pre_click_failures_leave_row_ready(tmp_path: Path, failure: str) -> None:
    path, _ = ready_tracker(tmp_path)
    CDP.dispatch(path, FakeSession(failure), 1)
    row = read_row(path)
    assert row["send_status"] == "ready"
    assert not row["send_attempt_id"]


@pytest.mark.parametrize("failure", ["click", "verify"])
def test_uncertain_delivery_requires_manual_review(tmp_path: Path, failure: str) -> None:
    path, _ = ready_tracker(tmp_path)
    CDP.dispatch(path, FakeSession(failure), 1)
    row = read_row(path)
    assert row["send_status"] == "manual_review"
    assert row["send_attempt_id"]
    assert row["last_error"]


def test_signed_out_preflight_changes_nothing(tmp_path: Path) -> None:
    path, original = ready_tracker(tmp_path)
    with pytest.raises(CDP.CdpError, match="signed out"):
        CDP.dispatch(path, FakeSession("signed_out"), 1)
    assert read_row(path) == original


def test_remote_cdp_requires_explicit_option() -> None:
    with pytest.raises(CDP.CdpError, match="Remote CDP"):
        CDP.validate_cdp_url("http://192.0.2.5:9222")
    assert CDP.validate_cdp_url("http://192.0.2.5:9222", allow_remote=True)


def test_recipient_matching_rejects_partial_names() -> None:
    assert CDP.recipient_matches("Asha Rao", "Asha Rao 1st degree connection")
    assert not CDP.recipient_matches("Ann Lee", "Anna Lee")


def test_selector_catalog_is_complete() -> None:
    selectors = CDP.load_selectors(SKILL_DIR / "references" / "linkedin-selectors.json")
    assert CDP.REQUIRED_SELECTOR_GROUPS <= selectors.keys()


def test_unavailable_cdp_endpoint_has_clear_error() -> None:
    selectors = CDP.load_selectors(SKILL_DIR / "references" / "linkedin-selectors.json")
    with pytest.raises(CDP.CdpError, match="Could not attach to Chrome CDP"):
        with CDP.PlaywrightChromeSession("http://127.0.0.1:9", selectors, timeout_ms=250):
            pass
