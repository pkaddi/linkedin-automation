from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = REPO_ROOT / "packaging" / "build.py"
SPEC = importlib.util.spec_from_file_location("outreach_package_builder", BUILD_PATH)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def test_builder_creates_all_platform_layouts_and_checksums(tmp_path: Path) -> None:
    output = tmp_path / "package"
    result = BUILDER.build(output)
    assert result["version"] == "0.2.0"
    assert (output / "chatgpt-work" / ".codex-plugin" / "plugin.json").is_file()
    assert (output / "claude-cowork" / ".claude-plugin" / "plugin.json").is_file()
    assert (output / "claude-marketplace" / ".claude-plugin" / "marketplace.json").is_file()
    assert (
        output
        / "claude-marketplace"
        / "plugins"
        / "linkedin-decision-maker-outreach"
        / ".claude-plugin"
        / "plugin.json"
    ).is_file()
    assert (output / "hermes-skill" / "SKILL.md").is_file()
    assert (output / "hermes-profile" / "distribution.yaml").is_file()
    assert (
        output
        / "hermes-profile"
        / "skills"
        / "linkedin-decision-maker-outreach"
        / "scripts"
        / "linkedin_cdp.py"
    ).is_file()
    assert (
        output
        / "hermes-profile"
        / "skills"
        / "linkedin-decision-maker-outreach"
        / "references"
        / "linkedin-selectors.json"
    ).is_file()

    manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["sha256"]) == set(result["artifacts"])
    for archive_name, expected in manifest["sha256"].items():
        archive = output / archive_name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            if archive_name.startswith("hermes-skill"):
                assert "SKILL.md" in names
            else:
                assert any(
                    name.endswith("skills/linkedin-decision-maker-outreach/SKILL.md")
                    for name in names
                )
            assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)

    with zipfile.ZipFile(output / "claude-cowork-0.2.0.zip") as package:
        assert ".claude-plugin/plugin.json" in package.namelist()
        assert any(name.endswith("scripts/linkedin_cdp.py") for name in package.namelist())
        assert any(name.endswith("references/linkedin-selectors.json") for name in package.namelist())
    with zipfile.ZipFile(output / "chatgpt-work-0.2.0.zip") as package:
        assert ".codex-plugin/plugin.json" in package.namelist()


def test_builder_is_deterministic(tmp_path: Path) -> None:
    first = BUILDER.build(tmp_path / "first")
    second = BUILDER.build(tmp_path / "second")
    assert first["sha256"] == second["sha256"]
