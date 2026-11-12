"""Regression tests for custom canonical rule paths."""

import argparse

import pytest

import agentsync.config as config_module
from agentsync import AgentSyncConfig, AgentSyncer, is_initialised
from agentsync.cli import cmd_adopt, cmd_diff, cmd_init, cmd_status, cmd_sync
from agentsync.config import CONFIG_FILE, RULES_FILE, read_rules, write_config, write_rules

CUSTOM_RULES = "# Team rules\n- Use tabs\n"


@pytest.fixture(params=["stdlib", "fallback"])
def custom_project(tmp_path, monkeypatch, request):
    if request.param == "fallback":
        monkeypatch.setattr(config_module, "tomllib", None)
    write_config(tmp_path, tools=["claude_md"])
    config_path = tmp_path / CONFIG_FILE
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(RULES_FILE, "docs/RULES.md"),
        encoding="utf-8",
    )
    rules_path = tmp_path / "docs/RULES.md"
    rules_path.parent.mkdir()
    rules_path.write_text(CUSTOM_RULES, encoding="utf-8")
    return tmp_path


def test_initialised_with_only_custom_rules(custom_project):
    assert not (custom_project / RULES_FILE).exists()
    assert is_initialised(custom_project)


def test_missing_custom_rules_do_not_fall_back_to_default(custom_project):
    (custom_project / "docs/RULES.md").unlink()
    (custom_project / RULES_FILE).write_text("# Old rules\n", encoding="utf-8")

    assert not is_initialised(custom_project)
    with pytest.raises(FileNotFoundError, match="docs/RULES.md"):
        read_rules(custom_project)


def test_read_rules_uses_custom_path_even_when_default_exists(custom_project):
    (custom_project / RULES_FILE).write_text("# Old rules\n", encoding="utf-8")
    assert read_rules(custom_project) == CUSTOM_RULES


def test_write_rules_uses_custom_path(custom_project):
    write_rules("# Updated rules\n", root=custom_project)
    assert (custom_project / "docs/RULES.md").read_text(encoding="utf-8") == "# Updated rules\n"
    assert not (custom_project / RULES_FILE).exists()


def test_sync_and_status_use_custom_rules(custom_project):
    syncer = AgentSyncer(root=custom_project)
    report = syncer.sync()
    assert report.created == 1
    assert report.canonical_path == str(custom_project / "docs/RULES.md")
    assert CUSTOM_RULES in (custom_project / "CLAUDE.md").read_text(encoding="utf-8")
    assert syncer.status()[0]["status"] == "ok"

    (custom_project / "docs/RULES.md").write_text("# Changed rules\n", encoding="utf-8")
    assert syncer.status()[0]["status"] == "stale"
    assert syncer.sync().updated == 1


def test_sync_uses_explicit_config_without_a_config_file(tmp_path):
    rules_path = tmp_path / "team.md"
    rules_path.write_text(CUSTOM_RULES, encoding="utf-8")
    config = AgentSyncConfig(root=tmp_path, canonical="team.md", tools=["claude_md"])
    syncer = AgentSyncer(root=tmp_path, config=config)

    assert syncer.sync().created == 1
    assert CUSTOM_RULES in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert syncer.status()[0]["status"] == "ok"
    rules_path.write_text("# Changed rules\n", encoding="utf-8")
    assert syncer.status()[0]["status"] == "stale"


@pytest.mark.parametrize("canonical", [".github/copilot-instructions.md", "team.md"])
def test_sync_never_writes_to_canonical_output(tmp_path, canonical):
    output = tmp_path / ".github/copilot-instructions.md"
    output.parent.mkdir()
    output.write_text(CUSTOM_RULES, encoding="utf-8")
    rules_path = tmp_path / canonical
    if rules_path != output:
        rules_path.hardlink_to(output)
    config = AgentSyncConfig(root=tmp_path, canonical=canonical, tools=["copilot", "claude_md"])
    syncer = AgentSyncer(root=tmp_path, config=config)

    assert syncer.sync(dry_run=True).created == 1
    assert not config.lock_path.exists()
    assert syncer.sync().created == 1
    assert syncer.sync().updated == 0
    assert rules_path.read_text(encoding="utf-8") == CUSTOM_RULES
    assert syncer.status() == [{"tool": "claude_md", "path": "CLAUDE.md", "status": "ok"}]
    assert not syncer.detect_unmanaged()
    assert output.relative_to(tmp_path).as_posix() not in (tmp_path / ".gitignore").read_text()


@pytest.mark.parametrize("command", [cmd_sync, cmd_status, cmd_diff])
def test_cli_accepts_custom_only_project(custom_project, monkeypatch, command):
    monkeypatch.chdir(custom_project)
    AgentSyncer(root=custom_project).sync()
    assert command(argparse.Namespace(verbose=False, dry_run=False)) == 0


def test_init_does_not_reset_custom_only_project(custom_project, monkeypatch):
    monkeypatch.chdir(custom_project)
    config_before = (custom_project / CONFIG_FILE).read_bytes()
    assert cmd_init(argparse.Namespace(force=False, tools=None)) == 0
    assert (custom_project / CONFIG_FILE).read_bytes() == config_before
    assert (custom_project / "docs/RULES.md").read_text(encoding="utf-8") == CUSTOM_RULES
    assert not (custom_project / RULES_FILE).exists()


def test_adopt_writes_to_custom_path(custom_project, monkeypatch, capsys):
    monkeypatch.chdir(custom_project)
    (custom_project / "CLAUDE.md").write_text("# Adopted rules\n", encoding="utf-8")
    assert cmd_adopt(argparse.Namespace()) == 0
    assert (custom_project / "docs/RULES.md").read_text(encoding="utf-8") == "# Adopted rules\n"
    assert "Saved to: docs/RULES.md" in capsys.readouterr().out
    assert not (custom_project / RULES_FILE).exists()
