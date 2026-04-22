# agentsync

**One source of truth for all your AI coding agent rule files.**

[![Tests](https://img.shields.io/badge/Tests-53%20passing-brightgreen?style=flat-square)](tests/)
[![PyPI](https://img.shields.io/pypi/v/agentsync?style=flat-square)](https://pypi.org/project/agentsync/)
[![Dependencies](https://img.shields.io/badge/Dependencies-zero-brightgreen?style=flat-square)](pyproject.toml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](pyproject.toml)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/-Linda_Oraegbunam-blue?logo=linkedin&style=flat-square)](https://www.linkedin.com/in/linda-oraegbunam/)

---

## The problem

Open a typical AI-assisted project and you'll find this:

```
AGENTS.md          ← OpenAI Codex, OpenCode
CLAUDE.md          ← Claude Code
.cursorrules       ← Cursor (legacy)
.cursor/rules/     ← Cursor (modern)
.github/copilot-instructions.md  ← GitHub Copilot
GEMINI.md          ← Gemini CLI
.windsurfrules     ← Windsurf
```

Almost the same content. In every file. Maintained separately. Drifting apart.

Every time you update your coding conventions, you update seven files.
Every time you add a team member using a different tool, you create another file.

**agentsync fixes this.**

---

## How it works

Edit one file. Run one command. Every tool gets the right format.

```bash
pip install rulesync
rulesync init      # sets up .agentsync/rules.md
rulesync sync      # generates all rule files
```

```
rulesync sync
--------------------------------------------------
  canonical: .agentsync/rules.md
  created:   7
  updated:   0
  unchanged: 0
--------------------------------------------------
  [+] AGENTS.md
  [+] CLAUDE.md
  [+] .cursorrules
  [+] .cursor/rules/main.mdc
  [+] .github/copilot-instructions.md
  [+] GEMINI.md
  [+] .windsurfrules
```

---

## Install

```bash
pip install rulesync
```

Zero dependencies. Pure Python 3.10+.

---

## Quick start

```bash
# 1. Initialise in your project
cd my-project
rulesync init

# 2. Edit the canonical rules file
nano .agentsync/rules.md   # or your editor of choice

# 3. Sync to all tools
rulesync sync

# 4. Check status any time
rulesync status

# 5. Preview changes before writing
rulesync sync --dry-run
```

---

## Commands

```bash
rulesync init              # initialise in current project
rulesync sync              # sync all tool files from canonical source
rulesync sync --dry-run    # preview what would change
rulesync diff              # alias for sync --dry-run
rulesync status            # check which files are out of sync
rulesync add gemini_md     # add a new tool
rulesync remove cursorrules  # remove a tool
rulesync list              # list all 9 supported tools
rulesync adopt             # adopt your existing rules as the canonical source
```

---

## Supported tools

| Tool | File generated | Notes |
|---|---|---|
| `agents_md` | `AGENTS.md` | Cross-tool standard, Claude Code, Codex, OpenCode |
| `claude_md` | `CLAUDE.md` | Claude Code native format |
| `cursorrules` | `.cursorrules` | Cursor legacy format |
| `cursor_mdc` | `.cursor/rules/main.mdc` | Cursor modern format with YAML frontmatter |
| `copilot` | `.github/copilot-instructions.md` | GitHub Copilot |
| `gemini_md` | `GEMINI.md` | Gemini CLI |
| `windsurf` | `.windsurfrules` | Windsurf |
| `aider` | `.aider.conf.yml` | Aider |
| `opencode` | `AGENTS.md` | OpenCode (uses AGENTS.md) |

---

## Migrating from existing files

Already have a `CLAUDE.md` or `.cursorrules`? Use `rulesync adopt` to import the best existing file as the canonical source:

```bash
rulesync init
rulesync adopt   # finds the most complete existing rule file and imports it
rulesync sync    # regenerate all other files from the canonical source
```

---

## Python API

```python
from agentsync import AgentSyncer

syncer = AgentSyncer()
report = syncer.sync()
print(report.summary())

# Check status
statuses = syncer.status()
for s in statuses:
    print(s["path"], s["status"])  # ok / stale / missing

# Dry run
report = syncer.sync(dry_run=True)
print(f"Would create: {report.created}, update: {report.updated}")
```

---

## Pre-commit hook

Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: agentsync
      name: agentsync
      entry: rulesync sync
      language: system
      pass_filenames: false
      always_run: true
```

Now every commit automatically regenerates your rule files if the canonical source changed.

---

## CI/CD integration

```yaml
- name: Check agent rules are in sync
  run: |
    pip install rulesync
    rulesync status
```

`rulesync status` exits with code 1 if any files are stale or missing — perfect for PR checks.

---

## The canonical format

`.agentsync/rules.md` is plain markdown — no special syntax to learn:

```markdown
# Project Rules

## Stack
- Python 3.11+, FastAPI, PostgreSQL

## Conventions
- Use type hints throughout
- Write docstrings for all public functions
- Follow PEP 8

## Testing
- Run: pytest tests/ -v
- Coverage > 80%
- All new features need tests

## Important constraints
- Never commit secrets or credentials
- Ask before refactoring across multiple files
```

agentsync translates this into the right format for each tool automatically.

---

## Why not just symlinks?

Symlinks break on Windows, don't survive git clones cleanly, and don't handle format differences between tools — Cursor's `.mdc` format needs YAML frontmatter, `.aider.conf.yml` is YAML not markdown. agentsync handles all of that.

---

**Linda Oraegbunam** | [LinkedIn](https://www.linkedin.com/in/linda-oraegbunam/) | [Twitter](https://twitter.com/Obie_Linda) | [GitHub](https://github.com/obielin)
