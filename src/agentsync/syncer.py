"""Core sync engine for agentsync."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentsync.config import AgentSyncConfig, load_config, read_rules
from agentsync.tools import ALL_TOOLS, Tool, get_tool


@dataclass
class SyncResult:
    """Result of syncing a single tool's output file."""

    tool_id: str
    tool_name: str
    output_path: str
    status: str  # 'created' | 'updated' | 'unchanged' | 'skipped' | 'error'
    error: str = ""

    @property
    def changed(self) -> bool:
        return self.status in ("created", "updated")

    @property
    def ok(self) -> bool:
        return self.status != "error"

    def __repr__(self) -> str:
        return f"SyncResult({self.tool_id!r}, {self.status}, {self.output_path!r})"


@dataclass
class SyncReport:
    """Report for a complete sync operation."""

    results: list[SyncResult]
    canonical_path: str
    sync_time_ms: float = 0.0
    dry_run: bool = False

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.status == "created")

    @property
    def updated(self) -> int:
        return sum(1 for r in self.results if r.status == "updated")

    @property
    def unchanged(self) -> int:
        return sum(1 for r in self.results if r.status == "unchanged")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def total(self) -> int:
        return len(self.results)

    def summary(self) -> str:
        lines = [
            "",
            "agentsync sync" + (" (dry run)" if self.dry_run else ""),
            "-" * 50,
            f"  canonical: {self.canonical_path}",
            f"  created:   {self.created}",
            f"  updated:   {self.updated}",
            f"  unchanged: {self.unchanged}",
        ]
        if self.errors:
            lines.append(f"  errors:    {self.errors}")
        lines.append("-" * 50)
        for r in self.results:
            icon = {
                "created": "[+]",
                "updated": "[~]",
                "unchanged": "[ ]",
                "skipped": "[s]",
                "error": "[!]",
            }.get(r.status, "[?]")
            lines.append(f"  {icon} {r.output_path}")
            if r.error:
                lines.append(f"      Error: {r.error}")
        lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"SyncReport(created={self.created}, updated={self.updated}, "
            f"unchanged={self.unchanged}, errors={self.errors})"
        )


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _read_lock(lock_path: Path) -> dict[str, Any]:
    if lock_path.exists():
        try:
            return json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_lock(lock_path: Path, data: dict[str, Any]) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _update_gitignore(root: Path, paths_to_ignore: list[str]) -> None:
    """Add generated paths to .gitignore if not already present."""
    gitignore_path = root / ".gitignore"
    marker = "# agentsync generated files"
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""

    if marker in existing:
        return

    additions = ["\n", marker]
    for p in paths_to_ignore:
        if p not in existing:
            additions.append(p)
    additions.append("")

    with gitignore_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(additions))


class AgentSyncer:
    """
    Sync canonical .agentsync/rules.md to all configured tool files.

    Example:
        syncer = AgentSyncer()
        report = syncer.sync()
        print(report.summary())
    """

    def __init__(
        self,
        root: Path | None = None,
        config: AgentSyncConfig | None = None,
        verbose: bool = False,
    ) -> None:
        self.root = root or Path.cwd()
        self.config = config or load_config(self.root)
        self.verbose = verbose

    def sync(self, dry_run: bool = False) -> SyncReport:
        """
        Sync canonical rules to all configured tool files.

        Args:
            dry_run: If True, compute what would change but don't write files

        Returns:
            SyncReport with per-tool results
        """
        t0 = time.time()
        canonical_content = read_rules(self.root)
        lock = _read_lock(self.config.lock_path)
        results: list[SyncResult] = []
        generated_paths: list[str] = []

        for tool_id in self.config.tools:
            try:
                tool = get_tool(tool_id)
            except KeyError as e:
                results.append(
                    SyncResult(
                        tool_id=tool_id,
                        tool_name=tool_id,
                        output_path="unknown",
                        status="error",
                        error=str(e),
                    )
                )
                continue

            for rel_path in tool.output_paths:
                result = self._sync_one(
                    tool=tool,
                    rel_path=rel_path,
                    content=canonical_content,
                    lock=lock,
                    dry_run=dry_run,
                )
                results.append(result)
                if result.ok:
                    generated_paths.append(rel_path)

        if not dry_run:
            # Update lock file
            new_lock = {
                "canonical_hash": _hash_content(canonical_content),
                "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tools": {r.output_path: _hash_content(canonical_content) for r in results if r.ok},
            }
            _write_lock(self.config.lock_path, new_lock)

            if self.config.auto_gitignore and generated_paths:
                try:
                    _update_gitignore(self.root, generated_paths)
                except Exception:
                    pass

        return SyncReport(
            results=results,
            canonical_path=str(self.config.canonical_path),
            sync_time_ms=round((time.time() - t0) * 1000, 2),
            dry_run=dry_run,
        )

    def status(self) -> list[dict[str, str]]:
        """
        Check which generated files are out of sync with the canonical source.

        Returns:
            List of dicts with tool_id, path, status
        """
        try:
            canonical_content = read_rules(self.root)
        except FileNotFoundError:
            return []

        canonical_hash = _hash_content(canonical_content)
        lock = _read_lock(self.config.lock_path)
        statuses = []

        for tool_id in self.config.tools:
            try:
                tool = get_tool(tool_id)
            except KeyError:
                continue
            for rel_path in tool.output_paths:
                abs_path = self.root / rel_path
                if not abs_path.exists():
                    statuses.append({"tool": tool_id, "path": rel_path, "status": "missing"})
                elif lock.get("tools", {}).get(rel_path) != canonical_hash:
                    statuses.append({"tool": tool_id, "path": rel_path, "status": "stale"})
                else:
                    statuses.append({"tool": tool_id, "path": rel_path, "status": "ok"})

        return statuses

    def detect_unmanaged(self) -> list[str]:
        """
        Find rule files that exist in the project but are not managed by agentsync.
        """
        known_paths: set[str] = set()
        for tool in ALL_TOOLS.values():
            for p in tool.output_paths:
                known_paths.add(p)

        unmanaged = []
        for p in known_paths:
            abs_path = self.root / p
            if abs_path.exists():
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                if "Generated by agentsync" not in content:
                    unmanaged.append(p)
        return unmanaged

    def _sync_one(
        self,
        tool: Tool,
        rel_path: str,
        content: str,
        lock: dict[str, Any],
        dry_run: bool,
    ) -> SyncResult:
        abs_path = self.root / rel_path
        try:
            generated = tool.generate(content)
        except Exception as e:
            return SyncResult(
                tool_id=tool.id,
                tool_name=tool.name,
                output_path=rel_path,
                status="error",
                error=f"Generation failed: {e}",
            )

        existing = (
            abs_path.read_text(encoding="utf-8", errors="replace") if abs_path.exists() else None
        )

        if existing == generated:
            return SyncResult(
                tool_id=tool.id,
                tool_name=tool.name,
                output_path=rel_path,
                status="unchanged",
            )

        if not dry_run:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(generated, encoding="utf-8")

        status = "created" if existing is None else "updated"
        return SyncResult(
            tool_id=tool.id,
            tool_name=tool.name,
            output_path=rel_path,
            status=status,
        )
