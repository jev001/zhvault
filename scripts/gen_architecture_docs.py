#!/usr/bin/env python3
"""Generate docs/harness/ops/architecture.md from the live tree (stdlib only).

Usage (repo root):
  python3 scripts/gen_architecture_docs.py
  make docs-arch
"""

from __future__ import annotations

import ast
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "docs" / "harness" / "ops" / "architecture.md"


def _py_modules(base: Path) -> list[str]:
    mods: list[str] = []
    for p in sorted(base.rglob("*.py")):
        if p.name == "__pycache__":
            continue
        rel = p.relative_to(base).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        mods.append(".".join(parts))
    return mods


def _packages(base: Path) -> dict[str, list[str]]:
    """Top-level package -> child module basenames."""
    tree: dict[str, list[str]] = {}
    for p in sorted(base.iterdir()):
        if p.name.startswith("_") or p.name == "__pycache__":
            continue
        if p.is_dir() and (p / "__init__.py").exists():
            kids = []
            for c in sorted(p.glob("*.py")):
                if c.name == "__init__.py":
                    continue
                kids.append(c.stem)
            tree[p.name] = kids
        elif p.is_file() and p.suffix == ".py" and p.name != "__init__.py":
            tree.setdefault("(top)", []).append(p.stem)
    return tree


def _source_classes() -> list[tuple[str, str]]:
    """(class_name, module) for Source subclasses under sources/."""
    out: list[tuple[str, str]] = []
    sources_dir = SRC / "sources"
    for path in sorted(sources_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)
            if "Source" in bases or any("Source" in x for x in bases):
                if node.name == "Source":
                    continue
                out.append((node.name, f"sources.{path.stem}"))
    return out


def _cli_commands() -> list[str]:
    text = (SRC / "cli" / "app.py").read_text(encoding="utf-8")
    # Rough: @app.command / @xxx_app.command("name"
    found = re.findall(
        r'@(?:app|auth_app|graph_app|edge_app|search_app|account_app)\.command\(\s*"([^"]+)"',
        text,
    )
    # Typer groups: auth set-cookie etc. — also capture function defs after command for bare names
    # Build friendly paths from context is hard; list raw command leaf names + known groups from file.
    groups: list[str] = []
    if "auth_app" in text:
        groups.append("auth set-cookie")
    for leaf in found:
        if leaf in ("set-cookie",):
            continue
        # map by nearby app variable is fragile; emit leaf and prefix heuristically
        groups.append(leaf)
    # Prefer explicit known CLI surface from AGENTS
    return [
        "zhvault auth set-cookie",
        "zhvault status",
        "zhvault backup",
        "zhvault resume",
        "zhvault graph rebuild|sync|query",
        "zhvault graph edge add|remove",
        "zhvault search index|semantic",
        "zhvault account plan|apply",
    ]


def _render(packages: dict[str, list[str]], sources: list[tuple[str, str]], mods: list[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pkg_lines = []
    for name, kids in packages.items():
        if name == "(top)":
            pkg_lines.append(f"- top-level modules: {', '.join(f'`{k}`' for k in kids)}")
        else:
            kid_s = ", ".join(f"`{k}`" for k in kids) if kids else "(package only)"
            pkg_lines.append(f"- `{name}/` — {kid_s}")

    src_lines = "\n".join(f"- `{cls}` (`{mod}`)" for cls, mod in sources)
    cli_lines = "\n".join(f"- `{c}`" for c in _cli_commands())

    # Mermaid: avoid spaces in node IDs
    arch = """```mermaid
flowchart TB
  subgraph cli_layer [CLI]
    TyperApp[cli.app Typer]
    Cmds[cmd_backup cmd_graph cmd_search cmd_account cmd_auth]
  end
  subgraph core [Core]
    Pipeline[pipeline.Pipeline]
    Parse[parse.normalize]
    Http[http_client.ZhihuClient]
    Auth[auth cookies people_ref]
  end
  subgraph sources_layer [Sources]
    Build[sources.build_sources]
    Member[MemberPagedSource]
    Coll[CollectionSource]
    Social[Following Followers]
  end
  subgraph persist [Storage and writers]
    Engine[StorageEngine sqlite json rocksdb]
    ContentW[writers.content]
    PersonW[writers.person]
    AssetW[writers.asset]
  end
  subgraph derived [Derived offline]
    Graph[graph rebuild query]
    Kuzu[graph_kuzu]
    Search[search index semantic]
  end
  subgraph mutate_layer [Mutate danger]
    Plan[mutate.plan]
    Apply[mutate.apply]
  end
  TyperApp --> Cmds
  Cmds --> Auth
  Cmds --> Build
  Cmds --> Pipeline
  Build --> Member
  Build --> Coll
  Build --> Social
  Build --> Http
  Pipeline --> Parse
  Pipeline --> Engine
  Pipeline --> ContentW
  Pipeline --> PersonW
  Pipeline --> AssetW
  AssetW --> Http
  Cmds --> Graph
  Graph --> Engine
  Graph --> Kuzu
  Cmds --> Search
  Search --> Engine
  Cmds --> Plan
  Cmds --> Apply
  Apply --> Http
```"""

    backup_flow = """```mermaid
flowchart TD
  start[zhvault backup] --> parseUser{--user set?}
  parseUser -->|no| me[GET /api/v4/me]
  parseUser -->|yes| pref[parse_people_ref]
  pref --> verify[GET /members/token]
  verify -->|fail| exit2[exit 2]
  verify --> ignoreUrl[Ignore url.json collections]
  me --> collSelf[url.json or --collection-id]
  ignoreUrl --> discover[Discover member collections if needed]
  collSelf --> build[build_sources]
  discover --> build
  build --> pipe[Pipeline.run]
  pipe --> items[process_item writers]
  items --> meta[StorageEngine meta]
  items --> md[contents markdown]
  items --> assets[assets files]
  pipe --> summary[event summary JSON]
```"""

    data_layout = """```mermaid
flowchart LR
  dataDir[data/]
  dataDir --> contents[contents/owner_kind/...]
  dataDir --> assetsDir[assets/sha16.ext]
  dataDir --> meta[meta/engine/]
  dataDir --> logs[logs/]
  dataDir --> run[run/job.pid]
  meta --> sqlite[sqlite/state.sqlite]
  meta --> vectors[vectors/]
  meta --> kuzu[graph_query/kuzu/]
```"""

    gate_flow = """```mermaid
flowchart TD
  change[Code change] --> gate[make gate]
  gate --> ruff[ruff check src tests]
  gate --> pytest[pytest]
  ruff --> ok{exit 0?}
  pytest --> ok
  ok -->|yes| commit[git commit hooks on]
  ok -->|no| fix[Fix and retry]
  fix --> gate
  commit --> ci[CI harness-gate]
```"""

    return f"""# Project architecture (generated)

<!-- Generated by scripts/gen_architecture_docs.py — do not edit by hand; re-run make docs-arch -->
Generated-at: `{now}` (UTC)

Scan root: `src/` ({len(mods)} import modules).

## Package map

{chr(10).join(pkg_lines)}

## Source classes

{src_lines or "- (none found)"}

## CLI surface

{cli_lines}

## Architecture diagram

{arch}

## End-to-end backup flow

{backup_flow}

## Data layout

{data_layout}

## Harness green gate

{gate_flow}

## Related ops docs

- [README.md](./README.md) — ops index
- [flows.md](./flows.md) — confirmed product flowcharts (hand-maintained)
- [runbook.md](./runbook.md) — operator steps

## Regenerate

```bash
make docs-arch
# or: python3 scripts/gen_architecture_docs.py
```
"""


def main() -> int:
    if not SRC.is_dir():
        print(f"error: missing {SRC}", file=sys.stderr)
        return 2
    packages = _packages(SRC)
    sources = _source_classes()
    mods = _py_modules(SRC)
    text = _render(packages, sources, mods)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text)} bytes, {len(mods)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
