from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRACKER_SCRIPT = (
    REPO_ROOT
    / "skills"
    / "linkedin-decision-maker-outreach"
    / "scripts"
    / "outreach_tracker.py"
)


def run_tracker(*args: object, expected: int = 0) -> dict:
    process = subprocess.run(
        [sys.executable, str(TRACKER_SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == expected, process.stdout + process.stderr
    output = process.stdout if process.returncode == 0 else process.stderr
    return json.loads(output)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fixture_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    offer = tmp_path / "offer.md"
    roles = tmp_path / "roles.txt"
    connections = tmp_path / "Connections.csv"
    tracker = tmp_path / "outreach.csv"
    offer.write_text("# Offer\nReduce manual reporting time for operations teams.\n", encoding="utf-8")
    roles.write_text("CEO\nHead of Operations\n", encoding="utf-8")
    connections.write_text(
        "Notes:\n"
        "When exporting your connection data, some email addresses may be missing.\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Asha,Rao,https://www.linkedin.com/in/asha-rao,asha@example.com,Acme,Head of Operations,01 Jan 2026\n"
        "Ben,Shah,https://www.linkedin.com/in/ben-shah,ben@example.com,Beta,Engineer,02 Jan 2026\n"
        "=FORMULA,Patel,https://www.linkedin.com/in/formula-patel,formula@example.com,Gamma,Chief Executive Officer,03 Jan 2026\n",
        encoding="utf-8",
    )
    return offer, roles, connections, tracker


def initialize(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    offer, roles, connections, tracker = fixture_files(tmp_path)
    result = run_tracker(
        "init",
        "--offer",
        offer,
        "--connections",
        connections,
        "--roles",
        roles,
        "--output",
        tracker,
    )
    assert result["connections"] == 3
    return tracker, read_rows(tracker)


def prepare_approved_row(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    tracker, rows = initialize(tmp_path)
    target = next(row for row in rows if row["full_name"] == "Asha Rao")
    run_tracker(
        "set-draft",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--company-website",
        "https://acme.example",
        "--research-summary",
        "Acme is hiring analysts for its operations team.",
        "--source",
        "https://acme.example/careers",
        "--hook",
        "Acme is expanding its operations reporting team.",
        "--message",
        "Hi Asha, I saw Acme is growing its operations team. We help reduce manual reporting time. Would a short comparison be useful?",
    )
    rows = read_rows(tracker)
    target = next(row for row in rows if row["record_id"] == target["record_id"])
    target["approval_status"] = "approved"
    write_rows(tracker, rows)
    run_tracker("seal", "--tracker", tracker, "--record-id", target["record_id"])
    target = next(row for row in read_rows(tracker) if row["record_id"] == target["record_id"])
    return tracker, target


def test_init_filters_roles_and_excludes_email(tmp_path: Path) -> None:
    tracker, rows = initialize(tmp_path)
    assert "email" not in {column.lower() for column in rows[0]}
    by_name = {row["full_name"]: row for row in rows}
    assert by_name["Asha Rao"]["role_match"] == "yes"
    assert by_name["Ben Shah"]["role_match"] == "no"
    assert by_name["'=FORMULA Patel"]["role_match"] == "yes"
    run_tracker("validate", "--tracker", tracker)


def test_repeat_import_keeps_research_and_draft(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    run_tracker(
        "init",
        "--offer",
        tmp_path / "offer.md",
        "--connections",
        tmp_path / "Connections.csv",
        "--roles",
        tmp_path / "roles.txt",
        "--output",
        tracker,
    )
    refreshed = next(row for row in read_rows(tracker) if row["record_id"] == target["record_id"])
    assert refreshed["research_status"] == "complete"
    assert refreshed["research_summary"] == "Acme is hiring analysts for its operations team."
    assert refreshed["research_sources"] == "https://acme.example/careers"
    assert refreshed["draft_message"] == target["draft_message"]
    assert refreshed["approval_status"] == "approved"
    assert refreshed["send_status"] == "ready"


def test_role_mismatch_cannot_receive_a_draft_or_become_ready(tmp_path: Path) -> None:
    tracker, rows = initialize(tmp_path)
    target = next(row for row in rows if row["full_name"] == "Ben Shah")
    failed = run_tracker(
        "set-draft",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--company-website",
        "https://beta.example",
        "--research-summary",
        "Beta publishes software products.",
        "--source",
        "https://beta.example/about",
        "--hook",
        "Beta publishes software products.",
        "--message",
        "Hi Ben, would a short comparison be useful?",
        expected=2,
    )
    assert "role_match=yes" in failed["error"]
    assert run_tracker("ready", "--tracker", tracker)["count"] == 0


def test_message_longer_than_eighty_words_is_rejected(tmp_path: Path) -> None:
    tracker, rows = initialize(tmp_path)
    target = next(row for row in rows if row["full_name"] == "Asha Rao")
    failed = run_tracker(
        "set-draft",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--company-website",
        "https://acme.example",
        "--research-summary",
        "Acme publishes an operations product.",
        "--source",
        "https://acme.example/product",
        "--hook",
        "Acme publishes an operations product.",
        "--message",
        " ".join(["word"] * 81),
        expected=2,
    )
    assert "limit is 80" in failed["error"]


def test_approval_hash_allows_exact_send_state_transition(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    payload_hash = target["approved_payload_sha256"]
    ready = run_tracker("ready", "--tracker", tracker, "--limit", 5)
    assert ready["ready"][0]["draft_message"] == target["draft_message"]
    run_tracker(
        "begin-send",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--expected-payload-sha",
        payload_hash,
    )
    sent = run_tracker(
        "mark-sent",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--expected-payload-sha",
        payload_hash,
    )
    assert sent["send_status"] == "sent"
    run_tracker("validate", "--tracker", tracker)


def test_changed_message_is_not_ready_under_old_approval(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    rows = read_rows(tracker)
    row = next(row for row in rows if row["record_id"] == target["record_id"])
    row["draft_message"] += " Thanks."
    write_rows(tracker, rows)
    failed = run_tracker("ready", "--tracker", tracker, expected=2)
    assert "changed after approval" in failed["error"]
    run_tracker("validate", "--tracker", tracker, expected=2)


def test_uncertain_send_requires_manual_review_and_limit_is_enforced(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    run_tracker("ready", "--tracker", tracker, "--limit", 6, expected=2)
    run_tracker(
        "begin-send",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--expected-payload-sha",
        target["approved_payload_sha256"],
    )
    failed = run_tracker(
        "mark-failed",
        "--tracker",
        tracker,
        "--record-id",
        target["record_id"],
        "--error",
        "The connector timed out after accepting the write.",
    )
    assert failed["send_status"] == "manual_review"
    assert run_tracker("ready", "--tracker", tracker)["count"] == 0


def test_changed_offer_resets_an_unsent_approval(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    offer = tmp_path / "offer.md"
    offer.write_text("# New offer\nA materially different promised result.\n", encoding="utf-8")
    run_tracker(
        "init",
        "--offer",
        offer,
        "--connections",
        tmp_path / "Connections.csv",
        "--roles",
        tmp_path / "roles.txt",
        "--output",
        tracker,
    )
    refreshed = next(row for row in read_rows(tracker) if row["record_id"] == target["record_id"])
    assert refreshed["approval_status"] == "pending"
    assert refreshed["send_status"] == "not_ready"
    assert refreshed["approved_message_sha256"] == ""


def test_changed_recipient_is_not_ready_under_old_approval(tmp_path: Path) -> None:
    tracker, target = prepare_approved_row(tmp_path)
    rows = read_rows(tracker)
    row = next(row for row in rows if row["record_id"] == target["record_id"])
    row["profile_url"] = "https://linkedin.com/in/a-different-person"
    write_rows(tracker, rows)
    failed = run_tracker("ready", "--tracker", tracker, expected=2)
    assert "recipient or message changed" in failed["error"]
