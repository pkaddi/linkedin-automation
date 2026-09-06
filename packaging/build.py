#!/usr/bin/env python3
"""Build one canonical outreach skill for supported distribution layouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


PACKAGE_ID = "linkedin-decision-maker-outreach"
VERSION = "0.2.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_SOURCE = REPO_ROOT / "skills"
GENERATED_MARKER = ".generated-by-linkedin-outreach-builder"
IGNORED_NAMES = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


CLAUDE_MARKETPLACE = {
    "name": "hermes-stuff",
    "description": "Portable, approval-gated business workflow plugins from Hermes Stuff.",
    "version": VERSION,
    "owner": {"name": "Hermes Stuff"},
    "plugins": [
        {
            "name": PACKAGE_ID,
            "source": f"./plugins/{PACKAGE_ID}",
            "description": (
                "Create sourced LinkedIn drafts in an approval CSV and send exact "
                "approved text through a user-managed Chrome CDP session."
            ),
            "version": VERSION,
        }
    ],
}

class BuildError(RuntimeError):
    """The source is unsafe or incomplete for distribution."""


def included_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.is_file() and path.suffix not in IGNORED_SUFFIXES:
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(source).as_posix())


def inspect_source() -> None:
    required = [
        REPO_ROOT / ".codex-plugin" / "plugin.json",
        REPO_ROOT / ".claude-plugin" / "plugin.json",
        REPO_ROOT / "distribution.yaml",
        REPO_ROOT / "SOUL.md",
        REPO_ROOT / "config.yaml",
        REPO_ROOT / "README.md",
        REPO_ROOT / "REQUIREMENTS.md",
        SKILLS_SOURCE / PACKAGE_ID / "SKILL.md",
        SKILLS_SOURCE / PACKAGE_ID / "scripts" / "outreach_tracker.py",
        SKILLS_SOURCE / PACKAGE_ID / "scripts" / "linkedin_cdp.py",
        SKILLS_SOURCE / PACKAGE_ID / "references" / "linkedin-selectors.json",
        SKILLS_SOURCE / PACKAGE_ID / "requirements.txt",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise BuildError("Missing canonical files: " + ", ".join(missing))

    banned_names = {".env", "auth.json", "credentials.json"}
    inspected = included_files(SKILLS_SOURCE)
    inspected.extend(path for path in required if path.is_file() and path not in inspected)
    for path in inspected:
        if path.name in banned_names:
            raise BuildError(f"Refusing to package sensitive file: {path}")
        raw = path.read_bytes()
        if b"[TODO:" in raw:
            raise BuildError(f"Unresolved placeholder in {path}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if str(REPO_ROOT) in text:
            raise BuildError(f"Machine-specific repository path in {path}")


def copy_tree(source: Path, destination: Path) -> None:
    for source_file in included_files(source):
        target = destination / source_file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def make_chatgpt(target: Path) -> None:
    copy_tree(SKILLS_SOURCE, target / "skills")
    (target / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / ".codex-plugin" / "plugin.json", target / ".codex-plugin" / "plugin.json")
    shutil.copy2(REPO_ROOT / "README.md", target / "README.md")
    shutil.copy2(REPO_ROOT / "REQUIREMENTS.md", target / "REQUIREMENTS.md")


def make_claude(target: Path) -> None:
    copy_tree(SKILLS_SOURCE, target / "skills")
    (target / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / ".claude-plugin" / "plugin.json", target / ".claude-plugin" / "plugin.json")
    shutil.copy2(REPO_ROOT / "README.md", target / "README.md")
    shutil.copy2(REPO_ROOT / "REQUIREMENTS.md", target / "REQUIREMENTS.md")


def make_hermes_skill(target: Path) -> None:
    copy_tree(SKILLS_SOURCE / PACKAGE_ID, target)


def make_claude_marketplace(target: Path) -> None:
    plugin_target = target / "plugins" / PACKAGE_ID
    plugin_target.mkdir(parents=True)
    make_claude(plugin_target)
    write_json(target / ".claude-plugin" / "marketplace.json", CLAUDE_MARKETPLACE)
    write_text(
        target / "README.md",
        f"""# Hermes Stuff Claude marketplace

Add this directory locally with `/plugin marketplace add .`, then install with
`/plugin install {PACKAGE_ID}@hermes-stuff`. Publish the exact directory as a Git
repository so users can replace `.` with its `OWNER/REPOSITORY` address.
""",
    )


def make_hermes_profile(target: Path) -> None:
    copy_tree(SKILLS_SOURCE, target / "skills")
    for name in ("distribution.yaml", "SOUL.md", "config.yaml", "README.md", "REQUIREMENTS.md"):
        shutil.copy2(REPO_ROOT / name, target / name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_zip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source_file in included_files(source):
            archive_name = source_file.relative_to(source).as_posix()
            info = zipfile.ZipInfo(archive_name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if os.access(source_file, os.X_OK) else 0o644) << 16
            archive.writestr(info, source_file.read_bytes())


def replace_generated(staged: Path, output: Path) -> None:
    if output.exists():
        marker = output / GENERATED_MARKER
        if not marker.is_file():
            raise BuildError(f"Refusing to replace unmarked directory: {output}")
        shutil.rmtree(output)
    staged.replace(output)


def build(output: Path) -> dict[str, object]:
    inspect_source()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{PACKAGE_ID}.", dir=output.parent))
    staged = stage_root / PACKAGE_ID
    staged.mkdir()
    try:
        builders = {
            "chatgpt-work": make_chatgpt,
            "claude-cowork": make_claude,
            "claude-marketplace": make_claude_marketplace,
            "hermes-skill": make_hermes_skill,
            "hermes-profile": make_hermes_profile,
        }
        for name, builder in builders.items():
            target = staged / name
            target.mkdir(parents=True)
            builder(target)

        for name in builders:
            deterministic_zip(staged / name, staged / f"{name}-{VERSION}.zip")

        checksums = {
            path.name: sha256_file(path)
            for path in sorted(staged.glob("*.zip"), key=lambda item: item.name)
        }
        write_json(
            staged / "release-manifest.json",
            {"name": PACKAGE_ID, "version": VERSION, "sha256": checksums},
        )
        write_text(staged / GENERATED_MARKER, f"{PACKAGE_ID} {VERSION}\n")
        replace_generated(staged, output)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)
    return {
        "output": str(output),
        "version": VERSION,
        "artifacts": sorted(checksums),
        "sha256": checksums,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "dist",
        help="Generated output directory.",
    )
    args = parser.parse_args()
    try:
        result = build(args.output)
    except (BuildError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
