"""Invalid settings must never silently enable the default tools."""

from __future__ import annotations

import sys

import pytest

from agentsync import config
from agentsync.cli import main


@pytest.fixture(params=["native", "fallback"])
def parser(request, monkeypatch):
    if request.param == "fallback":
        monkeypatch.setattr(config, "tomllib", None)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "contents",
    [
        '[agentsync]\ntools = ["claude_md"\n',
        '[agentsync\ntools = ["claude_md"]\n',
        '[agentsync]\ntools = ["claude_md" "copilot"]\n',
        '[agentsync]\ntools = ["claude_md",, "copilot"]\n',
        '[agentsync]\ntools = ["claude_md"] trailing\n',
        '[agentsync]\ncanonical = "unterminated\n',
        "[agentsync]\nauto_gitignore = tru\n",
        '[agentsync]\ntools = []\ntools = ["claude_md"]\n',
        "[agentsync]\ntools = []\n[agentsync]\ntools = []\n",
        '[agentsync]\ntools = "claude_md"\n',
        '[agentsync]\nauto_gitignore = "false"\n',
        "[agentsync]\ntools = [true]\n",
        '[agentsync]\ncanonical = "bad\\qescape"\n',
        '[agentsync]\ncanonical = "\\uD800"\n',
        "[agentsync]\ntools = [\n" + '    "claude_md", # entry\n' * 100,
    ],
)
def test_invalid_config_names_file(tmp_path, parser, contents):
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=r"config\.toml"):
        config.load_config(tmp_path)


@pytest.mark.parametrize(
    "command", [["sync"], ["status"], ["diff"], ["add", "aider"], ["remove", "claude_md"]]
)
def test_cli_rejects_invalid_config_without_writes(tmp_path, monkeypatch, capsys, parser, command):
    config.write_config(tmp_path, tools=["claude_md"])
    config.write_rules("# Keep my rules\n", root=tmp_path)
    (tmp_path / config.CONFIG_FILE).write_text('[agentsync]\ntools = ["claude_md"\n')
    (tmp_path / "CLAUDE.md").write_text("# Existing rules\n")
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["rulesync", *command])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    assert "config.toml" in capsys.readouterr().err
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("tools", ["claude,cursor", "claude_md,unknown", "claude_md,", ",", ""])
@pytest.mark.parametrize("existing", [False, True])
def test_init_rejects_unknown_tools_before_writing(tmp_path, monkeypatch, capsys, tools, existing):
    if existing:
        config.write_config(tmp_path, tools=["claude_md"])
        config.write_rules("# Keep my rules\n", root=tmp_path)
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["rulesync", "init", "--tools", tools, "--force"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    error = capsys.readouterr().err
    assert "Unknown tool" in error
    assert "claude_md" in error
    assert snapshot(tmp_path) == before


def test_init_accepts_valid_tools_with_whitespace(tmp_path, monkeypatch, parser):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["rulesync", "init", "--tools", "claude_md, copilot"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert config.load_config(tmp_path).tools == ["claude_md", "copilot"]


def test_valid_settings_and_comments(tmp_path, parser):
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_text(
        "[agentsync] # settings\n"
        'version = "1.0.0"\n'
        "canonical = 'docs/#rules.md'\n"
        "tools = [\n  \"claude_md\", # one\n  'copilot',\n]\n"
        "auto_gitignore = false # true is only a comment\n"
        "warn_unmanaged = false\n",
        encoding="utf-8",
    )
    cfg = config.load_config(tmp_path)
    assert cfg.tools == ["claude_md", "copilot"]
    assert cfg.canonical == "docs/#rules.md"
    assert cfg.auto_gitignore is False
    assert cfg.warn_unmanaged is False


def test_empty_tools_stay_empty(tmp_path, parser):
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_text("[agentsync]\ntools = []\n")
    assert config.load_config(tmp_path).tools == []


def test_missing_config_still_uses_defaults(tmp_path, parser):
    assert config.load_config(tmp_path).tools == config.AgentSyncConfig().tools


def test_invalid_encoding_names_file(tmp_path, parser):
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_bytes(b"[agentsync]\n\xff")
    with pytest.raises(ValueError, match=r"config\.toml"):
        config.load_config(tmp_path)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_strings_and_unrelated_settings(tmp_path, parser, newline):
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_bytes(
        (
            'title = "ignored"\n'
            '[other]\ntools = ["ignored"]\n'
            "[agentsync]\n"
            'canonical = "docs/\\u65e5\\u672c#rules.md"\n'
            'tools = [\n "claude_md", # "aider" must stay a comment\n]\n'
            "warn_unmanaged = false"
        )
        .replace("\n", newline)
        .encode("utf-8")
    )
    cfg = config.load_config(tmp_path)
    assert cfg.canonical == "docs/日本#rules.md"
    assert cfg.tools == ["claude_md"]
    assert cfg.warn_unmanaged is False


def test_unreadable_config_names_file(tmp_path, monkeypatch, parser):
    config.write_config(tmp_path)

    def unreadable(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(type(tmp_path), "read_text", unreadable)
    with pytest.raises(ValueError, match=r"config\.toml.*permission denied"):
        config.load_config(tmp_path)


def test_fallback_rejects_unsupported_syntax(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "tomllib", None)
    path = tmp_path / config.CONFIG_FILE
    path.parent.mkdir()
    path.write_text('[agentsync]\ncanonical = """docs/rules.md"""\n')
    with pytest.raises(ValueError, match=r"config\.toml.*Python 3\.11\+"):
        config.load_config(tmp_path)
