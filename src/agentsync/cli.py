"""agentsync CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _ok(text: str) -> str:
    return _color(text, "92")


def _warn(text: str) -> str:
    return _color(text, "33")


def _err(text: str) -> str:
    return _color(text, "91")


def _dim(text: str) -> str:
    return _color(text, "2")


def cmd_init(args) -> int:
    from agentsync.config import (
        is_initialised,
        write_config,
        write_rules,
    )
    from agentsync.tools import DEFAULT_TOOLS

    root = Path.cwd()

    if is_initialised(root) and not args.force:
        print(f"{_warn('Already initialised.')} Use --force to reinitialise.")
        return 0

    tools = args.tools.split(",") if args.tools else DEFAULT_TOOLS
    write_config(root, tools=tools)
    write_rules(content=None, root=root)

    print(f"\n{_ok('agentsync initialised!')}\n")
    print(f"  Canonical rules: {_dim('.agentsync/rules.md')}")
    print(f"  Config:          {_dim('.agentsync/config.toml')}")
    print(f"  Tools:           {', '.join(tools)}")
    print()
    print(f"  Edit {_dim('.agentsync/rules.md')} then run:")
    print(f"  {_ok('agentsync sync')}")
    print()
    return 0


def cmd_sync(args) -> int:
    from agentsync import AgentSyncer
    from agentsync.config import is_initialised

    root = Path.cwd()
    if not is_initialised(root):
        print(_err("Not initialised. Run `agentsync init` first."))
        return 1

    syncer = AgentSyncer(root=root, verbose=args.verbose)
    report = syncer.sync(dry_run=args.dry_run)
    print(report.summary())

    if report.errors:
        return 1
    return 0


def cmd_status(args) -> int:
    from agentsync import AgentSyncer
    from agentsync.config import is_initialised

    root = Path.cwd()
    if not is_initialised(root):
        print(_err("Not initialised. Run `agentsync init` first."))
        return 1

    syncer = AgentSyncer(root=root)
    statuses = syncer.status()

    if not statuses:
        print(f"\n{_ok('All files up to date.')}\n")
        return 0

    print("\nagentsync status")
    print("-" * 50)
    any_stale = False
    for s in statuses:
        if s["status"] == "ok":
            print(f"  {_ok('[ok]')}      {s['path']}")
        elif s["status"] == "stale":
            print(f"  {_warn('[stale]')}   {s['path']}  (run `agentsync sync`)")
            any_stale = True
        elif s["status"] == "missing":
            print(f"  {_err('[missing]')}  {s['path']}  (run `agentsync sync`)")
            any_stale = True
    print()

    unmanaged = syncer.detect_unmanaged()
    if unmanaged and syncer.config.warn_unmanaged:
        print(_warn(f"  Warning: {len(unmanaged)} unmanaged rule file(s) found:"))
        for p in unmanaged:
            print(f"    {p}")
        print("  Run `agentsync adopt` to bring them under agentsync management.")
        print()

    return 1 if any_stale else 0


def cmd_diff(args) -> int:
    from agentsync import AgentSyncer
    from agentsync.config import is_initialised

    root = Path.cwd()
    if not is_initialised(root):
        print(_err("Not initialised. Run `agentsync init` first."))
        return 1

    syncer = AgentSyncer(root=root)
    report = syncer.sync(dry_run=True)

    if report.created == 0 and report.updated == 0:
        print(f"\n{_ok('No changes.')}\n")
        return 0

    print(report.summary())
    return 0


def cmd_add(args) -> int:
    from agentsync.config import load_config, write_config
    from agentsync.tools import ALL_TOOLS

    tool_id = args.tool
    if tool_id not in ALL_TOOLS:
        print(_err(f"Unknown tool: {tool_id!r}"))
        print(f"Available tools: {', '.join(sorted(ALL_TOOLS))}")
        return 1

    root = Path.cwd()
    cfg = load_config(root)

    if tool_id in cfg.tools:
        print(f"{_warn(f'{tool_id!r} is already configured.')}")
        return 0

    cfg.tools.append(tool_id)
    write_config(root, tools=cfg.tools)
    tool = ALL_TOOLS[tool_id]
    print(f"\n{_ok(f'Added {tool.name}')}")
    print(f"  Output: {', '.join(tool.output_paths)}")
    print(f"  Run {_dim('agentsync sync')} to generate the file.\n")
    return 0


def cmd_remove(args) -> int:
    from agentsync.config import load_config, write_config

    tool_id = args.tool
    root = Path.cwd()
    cfg = load_config(root)

    if tool_id not in cfg.tools:
        print(_warn(f"{tool_id!r} is not configured."))
        return 0

    cfg.tools.remove(tool_id)
    write_config(root, tools=cfg.tools)
    print(f"\n{_ok(f'Removed {tool_id!r} from configuration.')}")
    print("  Note: existing file was not deleted. Delete manually if needed.\n")
    return 0


def cmd_list(args) -> int:
    from agentsync.tools import ALL_TOOLS

    print(f"\nagentsync supports {len(ALL_TOOLS)} tools:\n")
    for tool_id, tool in sorted(ALL_TOOLS.items()):
        paths = ", ".join(tool.output_paths)
        print(f"  {tool_id:<20} {tool.name}")
        print(f"  {'':<20} {_dim(paths)}")
        if tool.notes:
            print(f"  {'':<20} {_dim(tool.notes)}")
        print()
    return 0


def cmd_adopt(args) -> int:
    """
    Adopt existing rule files into agentsync management.
    Reads the most complete existing file and uses it as the canonical source.
    """
    from agentsync.config import is_initialised, write_rules
    from agentsync.tools import ALL_TOOLS

    root = Path.cwd()
    if not is_initialised(root):
        print(_err("Not initialised. Run `agentsync init` first."))
        return 1

    # Find the largest existing rule file to use as canonical
    candidates = []
    for tool in ALL_TOOLS.values():
        for rel_path in tool.output_paths:
            abs_path = root / rel_path
            if abs_path.exists():
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                if "Generated by agentsync" not in content:
                    candidates.append((len(content), rel_path, content))

    if not candidates:
        print(_warn("No unmanaged rule files found."))
        return 0

    candidates.sort(reverse=True)
    best_len, best_path, best_content = candidates[0]
    write_rules(content=best_content, root=root)

    print(f"\n{_ok('Adopted canonical rules from:')} {best_path}")
    print(f"  Saved to: {_dim('.agentsync/rules.md')}")
    if len(candidates) > 1:
        print("\n  Other files found (not adopted):")
        for _, p, _ in candidates[1:]:
            print(f"    {_dim(p)}")
    print(f"\n  Run {_dim('agentsync sync')} to regenerate all files.\n")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="agentsync",
        description=(
            "One source of truth for all your AI coding agent rule files.\n"
            "Edit .agentsync/rules.md once. Generates AGENTS.md, CLAUDE.md,\n"
            ".cursorrules, .cursor/rules/main.mdc, copilot-instructions.md,\n"
            "GEMINI.md, and .windsurfrules automatically."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agentsync init              # initialise in current project
  agentsync sync              # sync all tool files from canonical source
  agentsync sync --dry-run    # preview changes without writing
  agentsync status            # check which files are out of sync
  agentsync diff              # alias for sync --dry-run
  agentsync add gemini_md     # add Gemini CLI support
  agentsync remove cursorrules  # remove a tool
  agentsync list              # list all supported tools
  agentsync adopt             # adopt existing rule files into agentsync
        """,
    )
    p.add_argument("--version", action="version", version="agentsync 1.0.0")

    sub = p.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialise agentsync in the current project")
    p_init.add_argument("--tools", help="Comma-separated list of tools to enable")
    p_init.add_argument("--force", action="store_true", help="Reinitialise even if already set up")
    p_init.set_defaults(func=cmd_init)

    # sync
    p_sync = sub.add_parser("sync", help="Sync canonical rules to all tool files")
    p_sync.add_argument("--dry-run", "-n", action="store_true", help="Preview without writing")
    p_sync.add_argument("--verbose", "-v", action="store_true")
    p_sync.set_defaults(func=cmd_sync)

    # status
    p_status = sub.add_parser("status", help="Show sync status of all tool files")
    p_status.set_defaults(func=cmd_status)

    # diff
    p_diff = sub.add_parser("diff", help="Preview what sync would change")
    p_diff.set_defaults(func=cmd_diff)

    # add
    p_add = sub.add_parser("add", help="Add a tool to the sync list")
    p_add.add_argument("tool", help="Tool ID (run `agentsync list` to see options)")
    p_add.set_defaults(func=cmd_add)

    # remove
    p_remove = sub.add_parser("remove", help="Remove a tool from the sync list")
    p_remove.add_argument("tool", help="Tool ID")
    p_remove.set_defaults(func=cmd_remove)

    # list
    p_list = sub.add_parser("list", help="List all supported AI coding tools")
    p_list.set_defaults(func=cmd_list)

    # adopt
    p_adopt = sub.add_parser("adopt", help="Adopt existing rule files into agentsync")
    p_adopt.set_defaults(func=cmd_adopt)

    args = p.parse_args()
    result = args.func(args)
    sys.exit(result if isinstance(result, int) else 0)


if __name__ == "__main__":
    main()
