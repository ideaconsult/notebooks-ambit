#!/usr/bin/env python
"""Read-only CLI: compute and save the ranked endpoint/parameter/unit
harmonization backlog.

Usage:
    python backlog_report.py [--env env.yaml] [--kind KIND] [--top N]

Reads `nanodata_root` / `folder_output` from an env.yaml (see
env_example.yaml — copy it to env.yaml, which is gitignored, and fill in
your local paths; nothing machine-specific belongs in this script).

No writes anywhere under nanodata/ or elsewhere in the source tree --
this only reads the '*-undefined_*.properties' reports already produced
by prior local import runs (see nanodata/AGENTS.md) and writes its own
output under folder_output.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from lib import undefined_reports as ur

# Windows consoles often default to a non-UTF-8 codepage, which would
# otherwise mangle the real unicode content (mu, degree sign, etc.) found
# in these unit/parameter strings.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def load_env(env_path: Path) -> dict:
    if not env_path.exists():
        example = env_path.with_name("env_example.yaml")
        raise SystemExit(
            f"{env_path} not found. Copy {example.name} to "
            f"{env_path.name} and fill in your local nanodata_root."
        )
    return yaml.safe_load(env_path.read_text(encoding="utf-8")) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env", type=Path, default=Path("env.yaml"),
        help="Path to env.yaml (default: ./env.yaml)",
    )
    parser.add_argument(
        "--kind", choices=ur.KINDS, default=None,
        help="Filter to one report kind",
    )
    parser.add_argument(
        "--top", type=int, default=30,
        help="How many ranked terms to print/save per kind",
    )
    args = parser.parse_args()

    env = load_env(args.env)
    nanodata_root = Path(env["nanodata_root"])
    folder_output = Path(env.get("folder_output", "products"))
    folder_output.mkdir(parents=True, exist_ok=True)

    entries = ur.load_backlog(nanodata_root)
    n_files = len(ur.find_report_files(nanodata_root))
    print(f"Loaded {len(entries)} backlog entries from "
          f"{n_files} report files\n")

    summary = ur.backlog_summary(nanodata_root)
    for kind in ur.KINDS:
        print(f"{kind:28s} {summary[kind]:6d} raw lines")
    print()

    kinds = [args.kind] if args.kind else list(ur.KINDS)
    # rank_backlog_current cross-checks against the live dictionaries and
    # drops terms that are stale (already fixed since the report was
    # last generated) -- confirmed ~1-3% of raw entries per kind.
    ranked_by_kind = {
        kind: ur.rank_backlog_current(nanodata_root, entries, kind=kind)
        for kind in kinds
    }

    for kind, ranked in ranked_by_kind.items():
        print(f"=== {kind} "
              f"(top {args.top} of {len(ranked)} distinct terms) ===")
        for t in ranked[: args.top]:
            projects = ",".join(t.projects)
            print(f"  {t.count:4d}x  [{projects}]  {t.raw!r}")
        print()

    # Persist the full (unfiltered by --top) ranking, so the report is
    # reusable beyond this one console run.
    json_path = folder_output / "backlog_report.json"
    json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "ranked": {
                    kind: [asdict(t) for t in ranked]
                    for kind, ranked in ranked_by_kind.items()
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Saved full ranking to {json_path}")


if __name__ == "__main__":
    main()
