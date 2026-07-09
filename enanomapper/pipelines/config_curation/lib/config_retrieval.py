"""Nearest-neighbor search over the real JSON config corpus, across the
sibling `nanodata-<project>` data repos the caller points at.

Per nanodata/AGENTS.md: "There are thousands of real, production configs
across these repos ... for almost any assay type, a working config for a
similar layout already exists -- find it and adapt it." This module is the
first, simple version of that search: filename/path keyword matching plus
grepping the PROTOCOL_TOP_CATEGORY / PROTOCOL_CATEGORY_CODE / PROTOCOL_ENDPOINT
values out of candidate JSON files, ranked by overlap with the query. No
embeddings -- that's the existing pipelines/curation/tasks/vocabulary.py
BioPortal-embedding pipeline's job for ontology terms, a different problem
(free-text term -> ontology candidate, not config -> similar config).

Which folders count as "the corpus" is deliberately not auto-derived (an
earlier version guessed every `nanodata-*` sibling of `nanodata_root`, which
also swept in unrelated repos sharing that name prefix, e.g. the
`nanodata-11ty-*` static-site builders -- large `node_modules` trees, no
JSON configs -- and scratch copies like `nanodata-momentum-clean`). Instead
the caller supplies an explicit `{project_name: repo_dir}` map (env.yaml's
`config_corpus_dirs`, see env_example.yaml).

Work is normally done one project at a time (per the user), and parsing the
full ~1100-file corpus takes ~12s -- too slow to redo on every tool call, and
usually unnecessary. So both the scan and its on-disk cache
(products/config_corpus/<project>.json) are per-project: search a single
project by passing `project=`, or omit it to pool every configured project
(slower, but occasionally useful for cross-project harmonization -- see
HANDOFF_MCP_SERVER.md/the approved plan's note that project-by-project work
has the downside of not harmonizing across everything).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_CATEGORY_FIELDS = (
    "PROTOCOL_TOP_CATEGORY",
    "PROTOCOL_CATEGORY_CODE",
    "PROTOCOL_ENDPOINT",
)

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


@dataclass(frozen=True)
class ConfigCandidate:
    path: Path
    project: str          # key from config_corpus_dirs, e.g. "gracious"
    categories: tuple[str, ...] = field(default_factory=tuple)
    # ^ extracted PROTOCOL_* values


def _extract_categories(json_path: Path) -> tuple[str, ...]:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    apps = (
        data.get("PROTOCOL_APPLICATIONS") if isinstance(data, dict) else None
    )
    if not isinstance(apps, list):
        return ()
    values = []
    for app in apps:
        if not isinstance(app, dict):
            continue
        for field_name in _CATEGORY_FIELDS:
            v = app.get(field_name)
            if isinstance(v, str):
                values.append(v)
    return tuple(values)


def scan_project(project: str, repo_dir: Path) -> list[ConfigCandidate]:
    """List every `*.json` config under one project's repo directory.

    Cheap metadata scan (path + PROTOCOL_* category strings), not a full
    parse/validate of every file -- pyambit_check.validate_file() is the
    validator, this is just retrieval.
    """
    return [
        ConfigCandidate(
            path=p, project=project, categories=_extract_categories(p)
        )
        for p in repo_dir.glob("**/*.json")
    ]


def _cache_file(cache_dir: Path, project: str) -> Path:
    return cache_dir / f"{project}.json"


def load_or_scan_project(
    project: str, repo_dir: Path, cache_dir: Path, *, refresh: bool = False
) -> list[ConfigCandidate]:
    """scan_project(), cached per-project to `cache_dir/<project>.json`.

    Pass refresh=True after configs for this project have changed (e.g.
    after wiring in a new/edited config) to force a rescan.
    """
    cache_path = _cache_file(cache_dir, project)
    if not refresh and cache_path.exists():
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if raw.get("repo_dir") == str(repo_dir):
            return [
                ConfigCandidate(
                    path=Path(c["path"]),
                    project=project,
                    categories=tuple(c["categories"]),
                )
                for c in raw["candidates"]
            ]

    candidates = scan_project(project, repo_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "repo_dir": str(repo_dir),
                "candidates": [
                    {"path": str(c.path), "categories": list(c.categories)}
                    for c in candidates
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return candidates


def load_or_scan_corpus(
    corpus_dirs: dict[str, Path],
    cache_dir: Path,
    *,
    project: str | None = None,
    refresh: bool = False,
) -> list[ConfigCandidate]:
    """The per-project cached scan, restricted to `project` if given, else
    every project in `corpus_dirs` pooled together.

    Restricting to one `project` (the common case) only touches that
    project's files and cache entry -- it does not scan or even look at the
    other configured repos.
    """
    if project is not None:
        if project not in corpus_dirs:
            raise KeyError(
                f"{project!r} not in config_corpus_dirs "
                f"(configured: {sorted(corpus_dirs)})"
            )
        return load_or_scan_project(
            project, corpus_dirs[project], cache_dir, refresh=refresh
        )

    candidates = []
    for name, repo_dir in corpus_dirs.items():
        candidates.extend(
            load_or_scan_project(name, repo_dir, cache_dir, refresh=refresh)
        )
    return candidates


@dataclass(frozen=True)
class RankedCandidate:
    path: Path
    project: str
    score: int
    matched_terms: tuple[str, ...]


def retrieve_similar_configs(
    corpus: list[ConfigCandidate],
    *,
    category: str | None = None,
    keywords: str | None = None,
    top: int = 5,
) -> list[RankedCandidate]:
    """Rank configs by keyword overlap against `category` and/or `keywords`.

    `category` is matched against each candidate's extracted PROTOCOL_*
    values (e.g. "PC_WATER_SOL_SECTION" or "dynamic dissolution"); `keywords`
    is matched against the full path (folder names carry assay-type
    information, e.g. .../wp3/size_TEM/...) and the same PROTOCOL_* values.
    Neither is required, but at least one should be given or every config
    scores 0 and the top-N is arbitrary.
    """
    query_words: set[str] = set()
    if category:
        query_words |= _words(category)
    if keywords:
        query_words |= _words(keywords)

    ranked = []
    for c in corpus:
        haystack_words = _words(str(c.path)) | _words(" ".join(c.categories))
        matched = query_words & haystack_words
        if matched:
            ranked.append(
                RankedCandidate(
                    path=c.path, project=c.project,
                    score=len(matched), matched_terms=tuple(sorted(matched)),
                )
            )
    ranked.sort(key=lambda r: (-r.score, str(r.path)))
    return ranked[:top]
