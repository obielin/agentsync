"""The diff command shows proposed edits without writing project files."""

import argparse

import pytest

from agentsync import AgentSyncer
from agentsync.cli import cmd_diff
from agentsync.config import write_config, write_rules


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(tmp_path, tools=["claude_md"])
    write_rules("# Rules\n- Use tabs\n", root=tmp_path)
    return tmp_path


def snapshot(root):
    return {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_diff_shows_added_and_removed_lines_without_writes(project, capsys):
    AgentSyncer(root=project).sync()
    write_rules("# Rules\n- Use spaces\n- New rule\n", root=project)
    before = snapshot(project)

    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "--- CLAUDE.md\n+++ CLAUDE.md\n@@" in output
    assert "\n-- Use tabs\n" in output
    assert "\n+- Use spaces\n" in output
    assert "\n+- New rule\n" in output
    assert snapshot(project) == before


def test_diff_shows_new_files_from_dev_null(project, capsys):
    before = snapshot(project)
    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "--- /dev/null\n+++ CLAUDE.md\n@@" in output
    assert "\n+- Use tabs\n" in output
    assert snapshot(project) == before


def test_diff_unchanged_files_reports_no_changes(project, capsys):
    AgentSyncer(root=project).sync()
    before = snapshot(project)
    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "No changes." in output
    assert "@@" not in output
    assert snapshot(project) == before


def test_diff_keeps_existing_empty_file_name(project, capsys):
    (project / "CLAUDE.md").write_text("", encoding="utf-8")
    before = snapshot(project)
    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "--- CLAUDE.md\n+++ CLAUDE.md\n@@" in output
    assert "/dev/null" not in output
    assert snapshot(project) == before


def test_diff_separates_line_without_final_newline(project, capsys):
    (project / "CLAUDE.md").write_text("old rule", encoding="utf-8")
    before = snapshot(project)
    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "\n-old rule\n\\ No newline at end of file\n" in output
    assert "\n+# Rules\n" in output
    assert snapshot(project) == before


def test_diff_keeps_unicode_separator_in_the_same_line(project, capsys):
    (project / "CLAUDE.md").write_text("# Rules\n- A\u2028B\n", encoding="utf-8")
    write_rules("# Rules\n- A\u2028C\n", root=project)

    assert cmd_diff(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    assert "\n-- A\u2028B\n" in output
    assert "\n+- A\u2028C\n" in output
    assert "\\ No newline at end of file" not in output
