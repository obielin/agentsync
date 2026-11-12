"""Regression tests for preserving configuration when adding or removing tools."""

import argparse

import pytest

import agentsync.config as config_module
from agentsync.cli import cmd_add, cmd_init, cmd_remove
from agentsync.config import CONFIG_FILE, load_config, write_config

CUSTOM_CONFIG = """\
# Team configuration: café
[other]
tools = ["unrelated"]

[agentsync]
version = "2.0.0"
canonical = "docs/RULES.md"
# Keep these preferences.
auto_gitignore = false
warn_unmanaged = false
tools = ["claude_md", "copilot"] # enabled tools
extra = "preserve me"

[agentsync.custom]
tools = ["also unrelated"]
"""


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("command", "tool", "expected_tools"),
    [
        (cmd_add, "aider", ["claude_md", "copilot", "aider"]),
        (cmd_remove, "copilot", ["claude_md"]),
    ],
)
def test_tool_changes_preserve_other_config(
    tmp_path, monkeypatch, newline, command, tool, expected_tools
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    before = CUSTOM_CONFIG.replace("\n", newline)
    config_path.write_bytes(before.encode("utf-8"))

    assert command(argparse.Namespace(tool=tool)) == 0

    cfg = load_config(tmp_path)
    assert cfg.tools == expected_tools
    assert cfg.version == "2.0.0"
    assert cfg.canonical == "docs/RULES.md"
    assert cfg.auto_gitignore is False
    assert cfg.warn_unmanaged is False
    after = config_path.read_bytes().decode("utf-8")
    old_array = 'tools = ["claude_md", "copilot"]'
    prefix, suffix = before.split(old_array)
    assert after.startswith(prefix)
    assert after.endswith(suffix)


@pytest.mark.parametrize("fallback", [False, True])
def test_remove_last_tool_keeps_empty_list(tmp_path, monkeypatch, fallback):
    monkeypatch.chdir(tmp_path)
    if fallback:
        monkeypatch.setattr(config_module, "tomllib", None)
    write_config(tmp_path, tools=["claude_md"])

    assert cmd_remove(argparse.Namespace(tool="claude_md")) == 0
    assert load_config(tmp_path).tools == []


@pytest.mark.parametrize("fallback", [False, True])
def test_write_config_accepts_empty_tools(tmp_path, monkeypatch, fallback):
    if fallback:
        monkeypatch.setattr(config_module, "tomllib", None)
    write_config(tmp_path, tools=[])
    assert load_config(tmp_path).tools == []


def test_add_preserves_comments_with_closing_brackets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    config_path.write_text(
        '[agentsync]\ntools = [\n    "claude_md", # ] is only a comment\n]\n'
        "auto_gitignore = false\n",
        encoding="utf-8",
    )
    assert cmd_add(argparse.Namespace(tool="aider")) == 0
    assert load_config(tmp_path).tools == ["claude_md", "aider"]
    assert load_config(tmp_path).auto_gitignore is False


def test_add_preserves_multiline_strings_with_config_examples(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    before = (
        'notes = """\n[agentsync]\ntools = ["copilot"]\n"""\n'
        '["agentsync"] # active table\n'
        "notes = '''\n[other]\ntools = [\"copilot\"]\n'''\n"
        "'tools' = ['claude_md']\nauto_gitignore = false\n"
    )
    config_path.write_text(before, encoding="utf-8")
    assert cmd_add(argparse.Namespace(tool="aider")) == 0
    assert load_config(tmp_path).tools == ["claude_md", "aider"]
    assert load_config(tmp_path).auto_gitignore is False
    after = config_path.read_text(encoding="utf-8")
    prefix, suffix = before.split("'tools' = ['claude_md']")
    assert after.startswith(prefix)
    assert after.endswith(suffix)


@pytest.mark.skipif(config_module.tomllib is None, reason="requires the native TOML parser")
@pytest.mark.parametrize(
    "content",
    [
        '[agentsync]\nextra = [\n  [1, 2]\n]\ntools = ["claude_md"]\n',
        '["\\u0061gentsync"]\n"\\u0074ools" = ["claude_md"]\n',
        'agentsync.tools = ["claude_md"]\n',
        'agentsync = { tools = ["claude_md"], warn_unmanaged = false }\n',
    ],
)
@pytest.mark.parametrize(
    ("command", "tool", "expected_tools"),
    [(cmd_add, "aider", ["claude_md", "aider"]), (cmd_remove, "claude_md", [])],
)
def test_tool_changes_preserve_alternate_toml_layouts(
    tmp_path, monkeypatch, content, command, tool, expected_tools
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    config_path.write_text(content, encoding="utf-8")

    assert command(argparse.Namespace(tool=tool)) == 0

    result = config_path.read_text(encoding="utf-8")
    expected = config_module.tomllib.loads(content)
    expected["agentsync"]["tools"] = expected_tools
    assert config_module.tomllib.loads(result) == expected
    prefix, suffix = content.split('["claude_md"]')
    assert result.startswith(prefix)
    assert result.endswith(suffix)


def test_fallback_leaves_unsupported_layout_untouched(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "tomllib", None)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    content = b'agentsync.tools = ["claude_md"]\r\n'
    config_path.write_bytes(content)

    assert cmd_add(argparse.Namespace(tool="aider")) == 1
    assert config_path.read_bytes() == content
    assert "Python 3.11" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content", ["[agentsync]\nauto_gitignore = false\n", "[other]\nkeep = true\n"]
)
def test_add_inserts_missing_tools_without_losing_existing_content(tmp_path, monkeypatch, content):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    config_path.write_text(content, encoding="utf-8")
    assert cmd_add(argparse.Namespace(tool="aider")) == 0
    assert content in config_path.read_text(encoding="utf-8")
    assert "aider" in load_config(tmp_path).tools


def test_force_init_still_writes_fresh_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / CONFIG_FILE
    config_path.parent.mkdir()
    config_path.write_text(CUSTOM_CONFIG, encoding="utf-8")
    assert cmd_init(argparse.Namespace(force=True, tools="claude_md")) == 0
    cfg = load_config(tmp_path)
    assert cfg.tools == ["claude_md"]
    assert cfg.auto_gitignore is True
    assert cfg.warn_unmanaged is True
    assert cfg.canonical == ".agentsync/rules.md"
