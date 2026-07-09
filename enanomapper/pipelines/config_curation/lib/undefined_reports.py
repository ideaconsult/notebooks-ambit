"""Aggregate the '<PREFIX>-undefined_<kind>.properties' backlog across all
projectdata-* modules.

These files are written by AbstractImportTest.storeUndefined() (ambit-git,
consumed as a Maven dependency by nanodata/projectdata-<project>) after
each JUnit import run: one raw string per line, per {endpoints,
protocol_parameters, protocol_parameter_values, units}, for every value
seen in the imported spreadsheet that had no entry in the corresponding
nanodata-common/.../net/idea/annotation/*.properties dictionary.

This module does not run the imports (see local_ambit.py) — it only reads
the reports already sitting on disk from whichever imports were last run
locally, and ranks them so the harmonization backlog can be prioritized by
how many projects/files a raw term actually blocks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from . import dictionaries as di
from . import javaprops

_FILENAME_RE = re.compile(
    r"^(?P<prefix>[A-Z0-9]+)-undefined_(?P<kind>.+)\.properties$"
)

KINDS = (
    "endpoints",
    "protocol_parameters",
    "protocol_parameter_values",
    "units",
)


@dataclass(frozen=True)
class UndefinedEntry:
    prefix: str        # project tag, e.g. "GRCS"
    kind: str          # one of KINDS
    raw: str           # raw, unmapped string as seen in the spreadsheet
    source_file: Path  # the *-undefined_*.properties file this came from


def find_report_files(nanodata_root: Path) -> list[Path]:
    """All '<PREFIX>-undefined_<kind>.properties' files under
    projectdata-* modules.

    These are written directly in each projectdata-<project> module root
    (not under src/...), e.g.
    nanodata/projectdata-harmless/HRMZ-undefined_endpoints.properties.
    """
    return sorted(
        nanodata_root.glob("projectdata-*/*-undefined_*.properties")
    )


def parse_report(path: Path) -> list[UndefinedEntry]:
    m = _FILENAME_RE.match(path.name)
    if not m or m.group("kind") not in KINDS:
        return []
    prefix, kind = m.group("prefix"), m.group("kind")
    entries = []
    for raw in javaprops.load(path).keys():
        if raw:
            entries.append(
                UndefinedEntry(
                    prefix=prefix, kind=kind, raw=raw, source_file=path
                )
            )
    return entries


def load_backlog(nanodata_root: Path) -> list[UndefinedEntry]:
    entries: list[UndefinedEntry] = []
    for f in find_report_files(nanodata_root):
        entries.extend(parse_report(f))
    return entries


@dataclass(frozen=True)
class RankedTerm:
    kind: str
    raw: str
    count: int                 # number of (prefix, source_file) hits
    projects: tuple[str, ...]  # distinct project prefixes, sorted


def rank_backlog(
    entries: list[UndefinedEntry], kind: str | None = None
) -> list[RankedTerm]:
    """Rank raw terms by how many projects/files they block, worst first.

    A term worth harmonizing first is one that shows up across many
    projects/files, not one seen once in a single obscure report.
    """
    grouped: dict[tuple[str, str], list[UndefinedEntry]] = defaultdict(list)
    for e in entries:
        if kind and e.kind != kind:
            continue
        grouped[(e.kind, e.raw)].append(e)

    ranked = [
        RankedTerm(
            kind=k,
            raw=raw,
            count=len(es),
            projects=tuple(sorted({e.prefix for e in es})),
        )
        for (k, raw), es in grouped.items()
    ]
    ranked.sort(key=lambda t: (-t.count, -len(t.projects), t.raw))
    return ranked


def rank_backlog_current(
    nanodata_root: Path,
    entries: list[UndefinedEntry],
    kind: str | None = None,
) -> list[RankedTerm]:
    """Like rank_backlog(), but cross-checked against the *current*
    dictionary state and with already-resolved terms dropped.

    The <PREFIX>-undefined_*.properties reports on disk are a snapshot
    from whenever each project's import test was last run locally --
    the shared dictionaries in nanodata-common/.../annotation/ (and
    nanodata/units.properties) keep evolving independently, so some
    "undefined" entries are stale: a fix already landed in the
    dictionary, the project just hasn't been re-imported since.
    Confirmed on the real backlog: ~1-3% of entries per kind are
    already resolved (e.g. PHYSICAL_STATE, ug/ml). Use this function
    (not the raw rank_backlog()) when proposing what to actually
    harmonize next, so the proposal list doesn't include already-fixed
    terms.
    """
    ranked = rank_backlog(entries, kind=kind)
    kinds = [kind] if kind else list(KINDS)
    dict_cache: dict[str, dict[str, str] | None] = {}
    for k in kinds:
        result = di.dictionary_for_kind(nanodata_root, k)
        dict_cache[k] = result[1] if result else None

    current = []
    for t in ranked:
        d = dict_cache.get(t.kind)
        if d is not None and di.lookup(d, t.raw) is not None:
            continue  # already resolved -- report is stale for this term
        current.append(t)
    return current


def backlog_summary(nanodata_root: Path) -> dict[str, int]:
    """Quick per-kind total line count, e.g. for a one-line sanity check."""
    entries = load_backlog(nanodata_root)
    summary = {k: 0 for k in KINDS}
    for e in entries:
        summary[e.kind] += 1
    return summary
