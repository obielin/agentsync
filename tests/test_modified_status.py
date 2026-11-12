"""Status must notice edits to generated files without changing the project."""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

from agentsync import ALL_TOOLS, AgentSyncer
from agentsync.cli import main
from agentsync.config import LOCK_FILE, write_config, write_rules


@pytest.fixture
def project(tmp_path):
    write_config(tmp_path, tools=["claude_md", "cursor_mdc"])
    write_rules("# Project Rules\n- Keep changes small.\n", root=tmp_path)
    AgentSyncer(root=tmp_path).sync()
    return tmp_path


def states(root):
    return {entry["path"]: entry["status"] for entry in AgentSyncer(root=root).status()}


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("path", ["CLAUDE.md", ".cursor/rules/main.mdc"])
@pytest.mark.parametrize("edit", ["append", "truncate", "line_endings", "invalid_utf8"])
def test_status_detects_manual_edits(project, path, edit):
    output = project / path
    original = output.read_bytes()
    changed = {
        "append": original + b"- Always use tabs.\n",
        "truncate": b"",
        "line_endings": (
            original.replace(b"\r\n", b"\n")
            if b"\r\n" in original
            else original.replace(b"\n", b"\r\n")
        ),
        "invalid_utf8": original + b"\xff",
    }[edit]
    output.write_bytes(changed)
    before = snapshot(project)

    status = states(project)

    assert status[path] == "modified"
    assert all(value == "ok" for key, value in status.items() if key != path)
    assert snapshot(project) == before


def test_sync_restores_generated_line_endings(project):
    output = project / "CLAUDE.md"
    original = output.read_bytes()
    edited = (
        original.replace(b"\r\n", b"\n")
        if b"\r\n" in original
        else original.replace(b"\n", b"\r\n")
    )
    output.write_bytes(edited)
    syncer = AgentSyncer(root=project)

    assert states(project)["CLAUDE.md"] == "modified"
    assert syncer.sync().updated == 1
    assert output.read_bytes() == original
    assert states(project)["CLAUDE.md"] == "ok"


def test_lock_records_each_output_content(project):
    lock = json.loads((project / LOCK_FILE).read_text())
    for path in ("CLAUDE.md", ".cursor/rules/main.mdc"):
        assert (
            lock["output_hashes"][path]
            == hashlib.sha256((project / path).read_bytes()).hexdigest()[:16]
        )
        assert lock["tools"][path] == lock["canonical_hash"]
    assert lock["output_hashes"]["CLAUDE.md"] != lock["output_hashes"][".cursor/rules/main.mdc"]


def test_modified_takes_precedence_over_stale(project):
    output = project / "CLAUDE.md"
    output.write_text(output.read_text() + "- My edit.\n")
    write_rules("# Updated Rules\n", root=project)
    assert states(project) == {"CLAUDE.md": "modified", ".cursor/rules/main.mdc": "stale"}


def test_missing_takes_precedence_over_modified(project):
    (project / "CLAUDE.md").unlink()
    assert states(project)["CLAUDE.md"] == "missing"


@pytest.mark.parametrize("edited", [False, True])
def test_legacy_lock_is_checked_without_rewriting(project, edited):
    lock_path = project / LOCK_FILE
    lock = json.loads(lock_path.read_text())
    lock.pop("output_hashes", None)
    lock_path.write_text(json.dumps(lock))
    if edited:
        output = project / "CLAUDE.md"
        output.write_text(output.read_text() + "- My edit.\n")
    before = snapshot(project)
    assert states(project)["CLAUDE.md"] == ("modified" if edited else "ok")
    assert snapshot(project) == before


def test_legacy_lock_with_changed_rules_remains_stale(project):
    lock_path = project / LOCK_FILE
    lock = json.loads(lock_path.read_text())
    lock.pop("output_hashes", None)
    lock_path.write_text(json.dumps(lock))
    write_rules("# Updated Rules\n", root=project)
    assert set(states(project).values()) == {"stale"}


def test_missing_lock_remains_stale(project):
    (project / LOCK_FILE).unlink()
    assert set(states(project).values()) == {"stale"}


def test_dry_run_does_not_clear_modified_status(project):
    output = project / "CLAUDE.md"
    output.write_text(output.read_text() + "- My edit.\n")
    before = snapshot(project)
    AgentSyncer(root=project).sync(dry_run=True)
    assert snapshot(project) == before
    assert states(project)["CLAUDE.md"] == "modified"


def test_real_sync_refreshes_hashes(project):
    output = project / "CLAUDE.md"
    output.write_text(output.read_text() + "- My edit.\n")
    AgentSyncer(root=project).sync()
    assert set(states(project).values()) == {"ok"}
    AgentSyncer(root=project).sync()
    assert set(states(project).values()) == {"ok"}


def test_cli_reports_modified_and_exits_one(project, monkeypatch, capsys):
    output = project / "CLAUDE.md"
    output.write_text(output.read_text() + "- My edit.\n")
    before = snapshot(project)
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["rulesync", "status"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "[modified]" in out and "CLAUDE.md" in out
    assert "review" in out.lower()
    assert snapshot(project) == before


@pytest.mark.parametrize("tool_id", sorted(ALL_TOOLS))
@pytest.mark.parametrize("legacy", [False, True])
def test_each_tool_detects_edits(tmp_path, tool_id, legacy):
    write_config(tmp_path, tools=[tool_id])
    write_rules("# Team Rules\n- Keep changes small.\n", root=tmp_path)
    AgentSyncer(root=tmp_path).sync()
    if legacy:
        lock_path = tmp_path / LOCK_FILE
        lock = json.loads(lock_path.read_text())
        lock.pop("output_hashes")
        lock_path.write_text(json.dumps(lock))
    assert set(states(tmp_path).values()) == {"ok"}
    for path in ALL_TOOLS[tool_id].output_paths:
        output = tmp_path / path
        output.write_text(output.read_text() + "# Local edit\n")
    assert set(states(tmp_path).values()) == {"modified"}
