#!/usr/bin/env python3
"""Manage the approval CSV for LinkedIn decision maker outreach.

This module owns tracker state and contains no browser code. The separate CDP
sender imports it so manual and automated delivery use the same validation and
approval checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "2"
MAX_MESSAGE_WORDS = 80

FIELDS = [
    "schema_version",
    "record_id",
    "first_name",
    "last_name",
    "full_name",
    "title",
    "company",
    "profile_url",
    "connected_on",
    "offer_sha256",
    "role_match",
    "matched_role",
    "role_reason",
    "company_website",
    "research_status",
    "research_summary",
    "research_sources",
    "personalization_hook",
    "draft_message",
    "draft_message_sha256",
    "approval_status",
    "approved_at",
    "approved_message_sha256",
    "approved_payload_sha256",
    "send_status",
    "send_started_at",
    "sent_at",
    "conversation_url",
    "send_attempt_id",
    "delivery_verified_at",
    "delivery_proof",
    "last_error",
    "updated_at",
]

SOURCE_FIELDS = {
    "first_name",
    "last_name",
    "full_name",
    "title",
    "company",
    "profile_url",
    "connected_on",
    "offer_sha256",
    "role_match",
    "matched_role",
    "role_reason",
}

APPROVALS = {"pending", "approved", "rejected"}
ROLE_MATCHES = {"yes", "no", "review"}
RESEARCH_STATES = {"pending", "complete", "skipped"}
SEND_STATES = {"not_ready", "ready", "sending", "sent", "manual_review"}
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class TrackerError(RuntimeError):
    """A validation error that should be shown without a traceback."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_import_text(value: object) -> str:
    text = clean_text(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def value_for_matching(value: str) -> str:
    return value[1:] if value.startswith("'") else value


def normalize_phrase(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def normalize_role_phrase(value: str) -> str:
    phrase = normalize_phrase(value)
    expansions = {
        "ceo": "chief executive officer",
        "coo": "chief operating officer",
        "cto": "chief technology officer",
        "cio": "chief information officer",
        "cfo": "chief financial officer",
        "cmo": "chief marketing officer",
        "cro": "chief revenue officer",
        "chro": "chief human resources officer",
        "svp": "senior vice president",
        "evp": "executive vice president",
        "vp": "vice president",
    }
    tokens: list[str] = []
    for token in phrase.split():
        tokens.extend(expansions.get(token, token).split())
    return " ".join(token for token in tokens if token not in {"of", "the"})


def normalize_profile_url(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if not re.match(r"^https?://", text, flags=re.IGNORECASE):
        text = "https://" + text.lstrip("/")
    parts = urlsplit(text)
    host = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    return urlunsplit(("https", host, path, "", ""))


def record_id_for(profile_url: str, full_name: str, company: str) -> str:
    identity = profile_url or f"{full_name.lower()}|{company.lower()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def message_sha(row: dict[str, str]) -> str:
    return sha256_text(row.get("draft_message", ""))


def payload_sha(row: dict[str, str]) -> str:
    payload = {
        "record_id": row.get("record_id", ""),
        "full_name": row.get("full_name", ""),
        "profile_url": row.get("profile_url", ""),
        "draft_message": row.get("draft_message", ""),
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def split_sources(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def validate_source_urls(sources: Iterable[str]) -> None:
    for source in sources:
        parts = urlsplit(source)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise TrackerError(f"Research source is not an HTTP URL: {source}")


def role_match(title: str, roles: list[str]) -> tuple[str, str, str]:
    normalized_title = normalize_role_phrase(value_for_matching(title))
    if not normalized_title:
        return "review", "", "The connection export has no title."
    matches = [role for role in roles if normalize_role_phrase(role) in normalized_title]
    if matches:
        return "yes", " | ".join(matches), f"Title contains: {', '.join(matches)}"
    return "no", "", "Title does not match a supplied decision maker role."


def read_roles(path: Path | None, inline_roles: list[str]) -> list[str]:
    roles = [clean_text(role) for role in inline_roles if clean_text(role)]
    if path:
        if not path.is_file():
            raise TrackerError(f"Roles file not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            role = clean_text(line)
            if role and not role.startswith("#"):
                roles.append(role)
    unique: list[str] = []
    seen: set[str] = set()
    for role in roles:
        key = normalize_phrase(role)
        if key and key not in seen:
            seen.add(key)
            unique.append(role)
    if not unique:
        raise TrackerError("Supply at least one decision maker role.")
    if any(role.startswith(FORMULA_PREFIXES) for role in unique):
        raise TrackerError("Decision maker roles cannot begin with a spreadsheet formula prefix.")
    return unique


def _header_index(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows[:30]):
        normalized = {normalize_phrase(cell) for cell in row}
        if "first name" in normalized and "last name" in normalized:
            return index
    raise TrackerError("Could not find the LinkedIn Connections.csv header row.")


def read_connections(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise TrackerError(f"Connections file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.reader(handle))
    header_index = _header_index(raw_rows)
    header = [normalize_phrase(cell) for cell in raw_rows[header_index]]
    records: list[dict[str, str]] = []
    for values in raw_rows[header_index + 1 :]:
        padded = values + [""] * max(0, len(header) - len(values))
        item = dict(zip(header, padded))
        first = safe_import_text(item.get("first name"))
        last = safe_import_text(item.get("last name"))
        full_name = clean_text(f"{first} {last}")
        profile_url = normalize_profile_url(item.get("url", ""))
        if profile_url:
            parts = urlsplit(profile_url)
            if not (
                (parts.netloc == "linkedin.com" or parts.netloc.endswith(".linkedin.com"))
                and parts.path.startswith("/in/")
            ):
                raise TrackerError(f"Unexpected non-profile LinkedIn URL in export: {profile_url}")
        company = safe_import_text(item.get("company"))
        if not full_name and not profile_url:
            continue
        records.append(
            {
                "first_name": first,
                "last_name": last,
                "full_name": safe_import_text(full_name),
                "title": safe_import_text(item.get("position")),
                "company": company,
                "profile_url": profile_url,
                "connected_on": safe_import_text(item.get("connected on")),
            }
        )
    if not records:
        raise TrackerError("The connection export contains no connection rows.")
    return records


def new_row(connection: dict[str, str], roles: list[str], offer_hash: str) -> dict[str, str]:
    match, matched, reason = role_match(connection["title"], roles)
    timestamp = now_iso()
    row = {field: "" for field in FIELDS}
    row.update(connection)
    row.update(
        {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id_for(
                connection["profile_url"], connection["full_name"], connection["company"]
            ),
            "offer_sha256": offer_hash,
            "role_match": match,
            "matched_role": matched,
            "role_reason": reason,
            "research_status": "pending" if match != "no" else "skipped",
            "approval_status": "pending",
            "send_status": "not_ready",
            "updated_at": timestamp,
        }
    )
    return row


def load_tracker(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise TrackerError(f"Tracker not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        legacy_fields = [
            field
            for field in FIELDS
            if field
            not in {"conversation_url", "send_attempt_id", "delivery_verified_at", "delivery_proof"}
        ]
        if reader.fieldnames not in (FIELDS, legacy_fields):
            raise TrackerError("Tracker columns do not match schema version 1 or 2.")
        rows = [{field: row.get(field, "") for field in FIELDS} for row in reader]
        if reader.fieldnames == legacy_fields:
            for row in rows:
                row["schema_version"] = SCHEMA_VERSION
    duplicates = [key for key, count in Counter(row["record_id"] for row in rows).items() if count > 1]
    if duplicates:
        raise TrackerError(f"Duplicate record_id values: {', '.join(duplicates)}")
    return rows


def write_tracker(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temp_name = handle.name
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def row_by_id(rows: list[dict[str, str]], record_id: str) -> dict[str, str]:
    for row in rows:
        if row["record_id"] == record_id:
            return row
    raise TrackerError(f"Unknown record_id: {record_id}")


def ensure_draft_is_safe(message: str) -> None:
    if not message.strip():
        raise TrackerError("Draft message is empty.")
    if message.lstrip().startswith(FORMULA_PREFIXES):
        raise TrackerError("Draft cannot begin with a spreadsheet formula prefix.")
    word_count = len(message.split())
    if word_count > MAX_MESSAGE_WORDS:
        raise TrackerError(f"Draft has {word_count} words. The limit is {MAX_MESSAGE_WORDS}.")


def validate_row(row: dict[str, str]) -> list[str]:
    errors: list[str] = []
    record_id = row.get("record_id", "<missing>")
    if row.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{record_id}: unsupported schema_version")
    if row.get("role_match") not in ROLE_MATCHES:
        errors.append(f"{record_id}: invalid role_match")
    if row.get("research_status") not in RESEARCH_STATES:
        errors.append(f"{record_id}: invalid research_status")
    if row.get("approval_status") not in APPROVALS:
        errors.append(f"{record_id}: invalid approval_status")
    if row.get("send_status") not in SEND_STATES:
        errors.append(f"{record_id}: invalid send_status")
    sources = split_sources(row.get("research_sources", ""))
    for source in sources:
        parts = urlsplit(source)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            errors.append(f"{record_id}: invalid research source {source}")
    if row.get("draft_message"):
        try:
            ensure_draft_is_safe(row["draft_message"])
        except TrackerError as exc:
            errors.append(f"{record_id}: {exc}")
        stored_sha = row.get("draft_message_sha256")
        if stored_sha and stored_sha != message_sha(row):
            errors.append(f"{record_id}: draft_message_sha256 does not match the draft")
    if row.get("approval_status") == "approved":
        if row.get("role_match") != "yes":
            errors.append(f"{record_id}: approved row is not a confirmed role match")
        if row.get("research_status") != "complete":
            errors.append(f"{record_id}: approved row has incomplete research")
        if not row.get("research_sources"):
            errors.append(f"{record_id}: approved row has no research source")
        if not row.get("approved_message_sha256"):
            errors.append(f"{record_id}: approved row has not been sealed")
        elif row["approved_message_sha256"] != message_sha(row):
            errors.append(f"{record_id}: approved message changed after approval")
        if not row.get("approved_payload_sha256"):
            errors.append(f"{record_id}: approved recipient and message have not been sealed")
        elif row["approved_payload_sha256"] != payload_sha(row):
            errors.append(f"{record_id}: approved recipient or message changed after approval")
    if row.get("send_status") in {"ready", "sending", "sent"}:
        if row.get("approval_status") != "approved":
            errors.append(f"{record_id}: send state requires approval")
        if row.get("approved_message_sha256") != message_sha(row):
            errors.append(f"{record_id}: send state does not match approved draft")
        if row.get("approved_payload_sha256") != payload_sha(row):
            errors.append(f"{record_id}: send state does not match approved recipient and draft")
    if row.get("send_status") == "sent" and not row.get("sent_at"):
        errors.append(f"{record_id}: sent row has no sent_at value")
    return errors


def validate_tracker(rows: list[dict[str, str]]) -> None:
    errors = [error for row in rows for error in validate_row(row)]
    if errors:
        raise TrackerError("Tracker validation failed:\n" + "\n".join(errors))


def command_init(args: argparse.Namespace) -> dict[str, object]:
    roles = read_roles(args.roles, args.role)
    if not args.offer.is_file():
        raise TrackerError(f"Offer file not found: {args.offer}")
    offer_hash = file_sha256(args.offer)
    connections = read_connections(args.connections)
    existing_rows = load_tracker(args.output) if args.output.exists() else []
    existing = {row["record_id"]: row for row in existing_rows}
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for connection in connections:
        fresh = new_row(connection, roles, offer_hash)
        record_id = fresh["record_id"]
        if record_id in seen:
            continue
        seen.add(record_id)
        prior = existing.get(record_id)
        if prior:
            if prior["send_status"] == "sent":
                merged.append(prior)
                continue
            changed = any(
                prior[field] != fresh[field]
                for field in {
                    "first_name",
                    "last_name",
                    "title",
                    "company",
                    "profile_url",
                    "offer_sha256",
                    "role_match",
                    "matched_role",
                }
            )
            for field in SOURCE_FIELDS:
                prior[field] = fresh[field]
            prior["schema_version"] = SCHEMA_VERSION
            prior["updated_at"] = now_iso()
            if changed or prior["role_match"] != "yes":
                prior["approval_status"] = "pending"
                prior["approved_at"] = ""
                prior["approved_message_sha256"] = ""
                prior["approved_payload_sha256"] = ""
                prior["send_status"] = "not_ready"
                prior["send_started_at"] = ""
                prior["conversation_url"] = ""
                prior["send_attempt_id"] = ""
                prior["delivery_verified_at"] = ""
                prior["delivery_proof"] = ""
                prior["last_error"] = "Source or offer changed; review the row again." if changed else ""
            merged.append(prior)
        else:
            merged.append(fresh)
    for prior in existing_rows:
        if prior["record_id"] not in seen:
            merged.append(prior)
    write_tracker(args.output, merged)
    counts = Counter(row["role_match"] for row in merged)
    return {
        "tracker": str(args.output),
        "connections": len(merged),
        "role_matches": dict(counts),
        "offer_sha256": offer_hash,
    }


def command_set_role(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    if row["send_status"] == "sent":
        raise TrackerError("A sent row cannot be reclassified.")
    row["role_match"] = args.match
    row["matched_role"] = safe_import_text(args.matched_role)
    row["role_reason"] = safe_import_text(args.reason)
    row["research_status"] = "pending" if args.match == "yes" else "skipped"
    row["approval_status"] = "pending"
    row["approved_at"] = ""
    row["approved_message_sha256"] = ""
    row["approved_payload_sha256"] = ""
    row["send_status"] = "not_ready"
    row["send_started_at"] = ""
    row["conversation_url"] = ""
    row["send_attempt_id"] = ""
    row["delivery_verified_at"] = ""
    row["delivery_proof"] = ""
    row["updated_at"] = now_iso()
    write_tracker(args.tracker, rows)
    return {"record_id": args.record_id, "role_match": args.match}


def command_set_draft(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    if row["role_match"] != "yes":
        raise TrackerError("Confirm role_match=yes before adding research and a draft.")
    if row["send_status"] == "sent":
        raise TrackerError("A sent row cannot receive a new first message draft.")
    message = clean_text(args.message)
    ensure_draft_is_safe(message)
    sources = [clean_text(source) for source in args.source if clean_text(source)]
    validate_source_urls(sources)
    if args.company_website:
        validate_source_urls([clean_text(args.company_website)])
    if not sources:
        raise TrackerError("Add at least one public research source URL.")
    summary = safe_import_text(args.research_summary)
    hook = safe_import_text(args.hook)
    if not summary or not hook:
        raise TrackerError("Research summary and personalization hook are required.")
    row.update(
        {
            "company_website": clean_text(args.company_website),
            "research_status": "complete",
            "research_summary": summary,
            "research_sources": " | ".join(sources),
            "personalization_hook": hook,
            "draft_message": message,
            "draft_message_sha256": sha256_text(message),
            "approval_status": "pending",
            "approved_at": "",
            "approved_message_sha256": "",
            "approved_payload_sha256": "",
            "send_status": "not_ready",
            "send_started_at": "",
            "conversation_url": "",
            "send_attempt_id": "",
            "delivery_verified_at": "",
            "delivery_proof": "",
            "last_error": "",
            "updated_at": now_iso(),
        }
    )
    write_tracker(args.tracker, rows)
    return {
        "record_id": args.record_id,
        "draft_message_sha256": row["draft_message_sha256"],
        "approval_status": "pending",
    }


def command_seal(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    targets = [row_by_id(rows, args.record_id)] if args.record_id else [
        row for row in rows if row["approval_status"] == "approved" and row["send_status"] != "sent"
    ]
    sealed: list[str] = []
    for row in targets:
        record_id = row["record_id"]
        if row["approval_status"] != "approved":
            raise TrackerError(f"{record_id}: approval_status must be approved")
        if row["role_match"] != "yes":
            raise TrackerError(f"{record_id}: role_match must be yes")
        if row["research_status"] != "complete" or not row["research_sources"]:
            raise TrackerError(f"{record_id}: research must be complete and sourced")
        ensure_draft_is_safe(row["draft_message"])
        current_sha = message_sha(row)
        existing_sha = row["approved_message_sha256"]
        if existing_sha and existing_sha != current_sha:
            raise TrackerError(f"{record_id}: approved message changed. Reset approval and review it again.")
        current_payload_sha = payload_sha(row)
        existing_payload_sha = row["approved_payload_sha256"]
        if existing_payload_sha and existing_payload_sha != current_payload_sha:
            raise TrackerError(
                f"{record_id}: approved recipient or message changed. Reset approval and review it again."
            )
        row["draft_message_sha256"] = current_sha
        row["approved_message_sha256"] = current_sha
        row["approved_payload_sha256"] = current_payload_sha
        row["approved_at"] = row["approved_at"] or now_iso()
        row["send_status"] = "ready"
        row["last_error"] = ""
        row["updated_at"] = now_iso()
        sealed.append(record_id)
    write_tracker(args.tracker, rows)
    return {"sealed": sealed, "count": len(sealed)}


def command_reject(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    if row["send_status"] in {"sending", "sent"}:
        raise TrackerError("A sending or sent row cannot be rejected here.")
    row["approval_status"] = "rejected"
    row["approved_at"] = ""
    row["approved_message_sha256"] = ""
    row["approved_payload_sha256"] = ""
    row["send_status"] = "not_ready"
    row["last_error"] = safe_import_text(args.reason)
    row["updated_at"] = now_iso()
    write_tracker(args.tracker, rows)
    return {"record_id": args.record_id, "approval_status": "rejected"}


def ready_row(row: dict[str, str]) -> dict[str, str]:
    errors = validate_row(row)
    if errors:
        raise TrackerError("\n".join(errors))
    if row["send_status"] != "ready":
        raise TrackerError(f"{row['record_id']}: send_status is not ready")
    return {
        "record_id": row["record_id"],
        "full_name": row["full_name"],
        "profile_url": row["profile_url"],
        "draft_message": row["draft_message"],
        "approved_message_sha256": row["approved_message_sha256"],
        "approved_payload_sha256": row["approved_payload_sha256"],
    }


def command_ready(args: argparse.Namespace) -> dict[str, object]:
    if not 1 <= args.limit <= 5:
        raise TrackerError("Ready limit must be between 1 and 5.")
    rows = load_tracker(args.tracker)
    selected = [row_by_id(rows, args.record_id)] if args.record_id else [
        row for row in rows if row["send_status"] == "ready"
    ]
    ready = [ready_row(row) for row in selected[: args.limit]]
    return {"ready": ready, "count": len(ready)}


def command_research_queue(args: argparse.Namespace) -> dict[str, object]:
    if not 1 <= args.limit <= 20:
        raise TrackerError("Research limit must be between 1 and 20.")
    rows = load_tracker(args.tracker)
    selected = [
        {
            "record_id": row["record_id"],
            "full_name": row["full_name"],
            "title": row["title"],
            "company": row["company"],
            "profile_url": row["profile_url"],
            "matched_role": row["matched_role"],
        }
        for row in rows
        if row["role_match"] == "yes"
        and row["research_status"] == "pending"
        and row["send_status"] != "sent"
    ][: args.limit]
    return {"research": selected, "count": len(selected)}


def command_begin_send(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    in_flight = [item["record_id"] for item in rows if item["send_status"] == "sending"]
    if in_flight:
        raise TrackerError(f"Another message is already sending: {in_flight[0]}")
    payload = ready_row(row)
    if args.expected_payload_sha != row["approved_payload_sha256"]:
        raise TrackerError("The expected payload hash does not match the approved recipient and draft.")
    row["send_status"] = "sending"
    row["send_started_at"] = now_iso()
    row["send_attempt_id"] = args.attempt_id or str(uuid.uuid4())
    row["conversation_url"] = ""
    row["delivery_verified_at"] = ""
    row["delivery_proof"] = ""
    row["last_error"] = ""
    row["updated_at"] = now_iso()
    write_tracker(args.tracker, rows)
    payload["send_status"] = "sending"
    payload["send_attempt_id"] = row["send_attempt_id"]
    return payload


def command_mark_sent(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    if row["send_status"] != "sending":
        raise TrackerError("mark-sent requires send_status=sending.")
    current_sha = message_sha(row)
    if (
        args.expected_payload_sha != payload_sha(row)
        or row["approved_payload_sha256"] != payload_sha(row)
        or row["approved_message_sha256"] != current_sha
    ):
        raise TrackerError("The sent recipient and message do not match the approved payload.")
    row["send_status"] = "sent"
    row["sent_at"] = now_iso()
    row["conversation_url"] = clean_text(args.conversation_url)
    row["delivery_verified_at"] = now_iso() if args.delivery_proof else ""
    row["delivery_proof"] = safe_import_text(args.delivery_proof)
    row["last_error"] = ""
    row["updated_at"] = now_iso()
    write_tracker(args.tracker, rows)
    return {
        "record_id": args.record_id,
        "send_status": "sent",
        "sent_at": row["sent_at"],
        "conversation_url": row["conversation_url"],
        "delivery_verified_at": row["delivery_verified_at"],
    }


def command_mark_failed(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    row = row_by_id(rows, args.record_id)
    if row["send_status"] != "sending":
        raise TrackerError("mark-failed requires send_status=sending.")
    row["send_status"] = "ready" if args.safe_to_retry else "manual_review"
    row["last_error"] = safe_import_text(args.error)
    row["updated_at"] = now_iso()
    write_tracker(args.tracker, rows)
    return {"record_id": args.record_id, "send_status": row["send_status"]}


def command_summary(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    return {
        "rows": len(rows),
        "role_match": dict(Counter(row["role_match"] for row in rows)),
        "research_status": dict(Counter(row["research_status"] for row in rows)),
        "approval_status": dict(Counter(row["approval_status"] for row in rows)),
        "send_status": dict(Counter(row["send_status"] for row in rows)),
    }


def command_validate(args: argparse.Namespace) -> dict[str, object]:
    rows = load_tracker(args.tracker)
    validate_tracker(rows)
    return {"valid": True, "rows": len(rows), "schema_version": SCHEMA_VERSION}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a LinkedIn outreach approval CSV.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create or refresh the tracker from Connections.csv.")
    init.add_argument("--connections", type=Path, required=True)
    init.add_argument("--offer", type=Path, required=True)
    init.add_argument("--roles", type=Path)
    init.add_argument("--role", action="append", default=[])
    init.add_argument("--output", type=Path, required=True)
    init.set_defaults(handler=command_init)

    set_role = subparsers.add_parser("set-role", help="Confirm or reject one role match.")
    set_role.add_argument("--tracker", type=Path, required=True)
    set_role.add_argument("--id", "--record-id", dest="record_id", required=True)
    set_role.add_argument("--match", choices=sorted(ROLE_MATCHES), required=True)
    set_role.add_argument("--matched-role", default="")
    set_role.add_argument("--reason", required=True)
    set_role.set_defaults(handler=command_set_role)

    set_draft = subparsers.add_parser("set-draft", help="Add sourced research and one draft.")
    set_draft.add_argument("--tracker", type=Path, required=True)
    set_draft.add_argument("--id", "--record-id", dest="record_id", required=True)
    set_draft.add_argument("--company-website", default="")
    set_draft.add_argument("--research-summary", required=True)
    set_draft.add_argument("--source", action="append", default=[], required=True)
    set_draft.add_argument("--hook", required=True)
    set_draft.add_argument("--message", required=True)
    set_draft.set_defaults(handler=command_set_draft)

    seal = subparsers.add_parser("seal", help="Seal rows the user marked approved in the CSV.")
    seal.add_argument("--tracker", type=Path, required=True)
    seal.add_argument("--id", "--record-id", dest="record_id")
    seal.set_defaults(handler=command_seal)

    reject = subparsers.add_parser("reject", help="Reject one draft.")
    reject.add_argument("--tracker", type=Path, required=True)
    reject.add_argument("--id", "--record-id", dest="record_id", required=True)
    reject.add_argument("--reason", default="Rejected by user.")
    reject.set_defaults(handler=command_reject)

    ready = subparsers.add_parser("ready", help="Print sealed rows that are ready to dispatch.")
    ready.add_argument("--tracker", type=Path, required=True)
    ready.add_argument("--id", "--record-id", dest="record_id")
    ready.add_argument("--limit", type=int, default=5)
    ready.set_defaults(handler=command_ready)

    research_queue = subparsers.add_parser(
        "research-queue", help="Print the next matched rows needing research and drafts."
    )
    research_queue.add_argument("--tracker", type=Path, required=True)
    research_queue.add_argument("--limit", type=int, default=20)
    research_queue.set_defaults(handler=command_research_queue)

    begin = subparsers.add_parser("begin-send", help="Lock one approved row before dispatch.")
    begin.add_argument("--tracker", type=Path, required=True)
    begin.add_argument("--id", "--record-id", dest="record_id", required=True)
    begin.add_argument("--expected-payload-sha", required=True)
    begin.add_argument("--attempt-id", default="")
    begin.set_defaults(handler=command_begin_send)

    sent = subparsers.add_parser("mark-sent", help="Mark sent after delivery is verified.")
    sent.add_argument("--tracker", type=Path, required=True)
    sent.add_argument("--id", "--record-id", dest="record_id", required=True)
    sent.add_argument("--expected-payload-sha", required=True)
    sent.add_argument("--conversation-url", default="")
    sent.add_argument("--delivery-proof", default="")
    sent.set_defaults(handler=command_mark_sent)

    failed = subparsers.add_parser("mark-failed", help="Record a failed or uncertain send.")
    failed.add_argument("--tracker", type=Path, required=True)
    failed.add_argument("--id", "--record-id", dest="record_id", required=True)
    failed.add_argument("--error", required=True)
    failed.add_argument("--safe-to-retry", action="store_true")
    failed.set_defaults(handler=command_mark_failed)

    summary = subparsers.add_parser("summary", help="Print tracker counts.")
    summary.add_argument("--tracker", type=Path, required=True)
    summary.set_defaults(handler=command_summary)

    validate = subparsers.add_parser("validate", help="Validate every tracker row.")
    validate.add_argument("--tracker", type=Path, required=True)
    validate.set_defaults(handler=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (OSError, TrackerError, csv.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
