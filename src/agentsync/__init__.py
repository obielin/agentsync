"""
agentsync
=========
One source of truth for all your AI coding agent rule files.

Edit .agentsync/rules.md once.
agentsync generates AGENTS.md, CLAUDE.md, .cursorrules,
.cursor/rules/main.mdc, .github/copilot-instructions.md,
GEMINI.md, and .windsurfrules automatically.

Zero dependencies. Pure Python 3.10+.

Quick start:
    agentsync init        # set up in current project
    agentsync sync        # generate all rule files from canonical source
    agentsync status      # check which files are out of sync
    agentsync diff        # see what would change
    agentsync add cursor  # add a new tool

Python API:
    from agentsync import AgentSyncer
    syncer = AgentSyncer()
    report = syncer.sync()
    print(report.summary())
"""

from agentsync.config import AgentSyncConfig, is_initialised, load_config
from agentsync.syncer import AgentSyncer, SyncReport, SyncResult
from agentsync.tools import ALL_TOOLS, DEFAULT_TOOLS, Tool

__version__ = "1.0.0"
__author__ = "Linda Oraegbunam"
__all__ = [
    "AgentSyncer",
    "AgentSyncConfig",
    "SyncReport",
    "SyncResult",
    "Tool",
    "ALL_TOOLS",
    "DEFAULT_TOOLS",
    "is_initialised",
    "load_config",
]
