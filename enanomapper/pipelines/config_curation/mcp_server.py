"""MCP server exposing the config_curation library as tools for a Claude
Code session working across nmdataparser/nanodata/ambit-git/pyambit.

Every tool here is a thin wrapper around lib/*.py -- read-only, or (for
dictionaries.propose_entry, reached via propose_dictionary_entry) a plain
file write that lands as a normal git diff for human review. Nothing here
calls an LLM: drafting/repairing a config is the calling Claude Code
session editing files directly, using these tools' output as context (see
HANDOFF_MCP_SERVER.md / the approved plan). AMBIT's process lifecycle
stays manual -- run_local_import only checks reachability and shells to
Maven against whatever is already running.

Config: reads nanodata_root / folder_output / config_corpus_dirs /
ambit_base_url from env.yaml next to this file (copy env_example.yaml).
metaenm Solr credentials come from the ENM_USER / ENM_PWD environment
variables (same convention as pipelines/metadata/env.dashboard.yaml).

Run directly for a stdio smoke test: `uv run python mcp_server.py`.
Register with Claude Code at user scope:
    claude mcp add --scope user config-curation -- \\
        uv run --project <this dir> python mcp_server.py
"""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from lib import config_lookup as cl
from lib import config_retrieval as cr
from lib import dictionaries as di
from lib import local_ambit as la
from lib import metaenm_search as ms
from lib import pyambit_check as pc
from lib import spreadsheet as sp
from lib import undefined_reports as ur

_ENV_PATH = Path(__file__).parent / "env.yaml"


def _load_env() -> dict[str, Any]:
    if not _ENV_PATH.exists():
        raise SystemExit(
            f"{_ENV_PATH} not found. Copy env_example.yaml to env.yaml "
            "and fill in your local paths."
        )
    return yaml.safe_load(_ENV_PATH.read_text(encoding="utf-8")) or {}


_env = _load_env()
NANODATA_ROOT = Path(_env["nanodata_root"])
FOLDER_OUTPUT = Path(_env.get("folder_output", "products"))
AMBIT_BASE_URL = _env.get("ambit_base_url", "http://localhost:9090/ambit2")
# No default: metaenm's URL is org-specific, not a public constant --
# every deployment must set it explicitly in env.yaml (see
# env_example.yaml). search_metaenm reports a clear error if unset.
METAENM_SOLR_URL = _env.get("metaenm_solr_url")
# {project_name: repo_dir} -- explicit and user-editable (env.yaml), not
# auto-derived; see lib/config_retrieval.py's module docstring for why.
CONFIG_CORPUS_DIRS = {
    name: Path(path)
    for name, path in _env.get("config_corpus_dirs", {}).items()
}
CORPUS_CACHE_DIR = FOLDER_OUTPUT / "config_corpus"

mcp = FastMCP("config-curation")


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses/Path/tuple results into plain
    JSON-safe dict/list/str, for MCP tool return values.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


# --- 1. find_config ------------------------------------------------------

@mcp.tool()
def find_config(
    excel_path: str, sheet: int | None = None, project: str | None = None
) -> dict:
    """Locate the driver-.properties line(s) referencing this Excel file
    (optionally one sheet) under nanodata/projectdata-<project>/.

    Returns status "active" (a working, enabled mapping exists),
    "disabled" (mapping exists but is commented out), or "not_found" (no
    mapping at all -- a candidate for authoring a new config), plus the
    matching line(s) with their properties file, line number, and target
    JSON config filename.
    """
    result = cl.find_config(
        NANODATA_ROOT, excel_path, sheet=sheet, project=project
    )
    return _to_jsonable(result)


# --- 2. retrieve_similar_configs ------------------------------------------

@mcp.tool()
def retrieve_similar_configs(
    category: str | None = None,
    keywords: str | None = None,
    project: str | None = None,
    top: int = 5,
    refresh: bool = False,
) -> dict:
    """Find existing real JSON configs similar to a target assay, by
    keyword overlap against PROTOCOL_TOP_CATEGORY /
    PROTOCOL_CATEGORY_CODE / PROTOCOL_ENDPOINT values and file path.

    Per nanodata/AGENTS.md, "for almost any assay type, a working config
    for a similar layout already exists -- find it and adapt it."
    Restrict to one `project` (e.g. "gracious") to search only that
    project's repo -- much faster, and the common case since work is
    usually done project by project (cross-project search costs more and
    is occasionally useful for harmonization instead of repair).
    `refresh=True` forces a rescan if configs changed since the last
    search in this session.

    Requires config_corpus_dirs to be configured in env.yaml.
    """
    if not CONFIG_CORPUS_DIRS:
        return {
            "error": "config_corpus_dirs is not configured in env.yaml "
            "-- add {project_name: path/to/nanodata-<project>} entries "
            "(see env_example.yaml)."
        }
    if project is not None and project not in CONFIG_CORPUS_DIRS:
        return {
            "error": f"{project!r} not in env.yaml's config_corpus_dirs "
            f"(configured: {sorted(CONFIG_CORPUS_DIRS)})"
        }
    corpus = cr.load_or_scan_corpus(
        CONFIG_CORPUS_DIRS, CORPUS_CACHE_DIR, project=project, refresh=refresh
    )
    ranked = cr.retrieve_similar_configs(
        corpus, category=category, keywords=keywords, top=top
    )
    return {"results": _to_jsonable(ranked)}


# --- 3. read_spreadsheet ---------------------------------------------------

@mcp.tool()
def read_spreadsheet(
    path: str,
    sheet: int | str | None = None,
    header_rows: int = 3,
    sample_rows: int = 5,
) -> dict:
    """Preview an Excel file: sheet names, and for the selected sheet (or
    every sheet if none given), its row/column count plus the first
    `header_rows` + `sample_rows` rows of real cell values.

    `sheet` is a 1-based index (matching the driver-.properties '#N'
    convention) or a sheet name. Read-only -- never writes to the Excel
    file.
    """
    result = sp.read_spreadsheet(
        Path(path),
        sheet=sheet,
        header_rows=header_rows,
        sample_rows=sample_rows,
    )
    return _to_jsonable(result)


# --- 4. run_local_import ----------------------------------------------------

@mcp.tool()
def run_local_import(project: str, test_method: str | None = None) -> dict:
    """Pre-flight-check the local AMBIT instance, then run
    Import_<PREFIX>_test for `project` (the projectdata-<project> module
    suffix, e.g. "gracious") via Maven.

    Uses the class's `test_all` method by default if it has one, else
    runs the whole test class; pass `test_method` to target one method
    while iterating on a fix. AMBIT is never started/stopped here -- it
    must already be running (Eclipse or Tomcat, per
    nanodata/guide/README.md); this fails fast with a clear message if it
    isn't reachable. Does not itself diff the resulting undefined-report
    backlog -- call backlog_report() again after this to see the effect.
    """
    result = la.run_local_import(
        NANODATA_ROOT,
        project,
        ambit_base_url=AMBIT_BASE_URL,
        test_method=test_method,
    )
    return _to_jsonable(result)


# --- 5. pyambit_validate -----------------------------------------------------

@mcp.tool()
def pyambit_validate(json_path: str) -> dict:
    """Shape-validate one AMBIT JSON file with pyambit.

    Applies only to native AMBIT JSON ({"records": N, "substance": [...]}
    -- e.g. enmconvertor -O json output or the live AMBIT REST API), NOT
    to files under nanodata/sql/<project>/export_json/ (Solr-indexed
    JSON, a different shape that will always fail this validator).
    """
    result = pc.validate_file(Path(json_path))
    return _to_jsonable(result)


# --- 6. backlog_report ------------------------------------------------------

@mcp.tool()
def backlog_report(kind: str | None = None, top: int = 30) -> dict:
    """Ranked endpoint/parameter/parameter-value/unit harmonization
    backlog: raw strings with no dictionary entry, across all
    projectdata-* undefined-report files, ranked by how many
    projects/files each one blocks.

    Cross-checked against the *current* dictionaries
    (rank_backlog_current) so already-fixed terms are dropped even if the
    on-disk undefined-report is stale. `kind` filters to one of
    "endpoints", "protocol_parameters", "protocol_parameter_values",
    "units"; omit to get all four.
    """
    entries = ur.load_backlog(NANODATA_ROOT)
    kinds = [kind] if kind else list(ur.KINDS)
    ranked_by_kind = {
        k: ur.rank_backlog_current(NANODATA_ROOT, entries, kind=k)[:top]
        for k in kinds
    }
    return {
        "summary": ur.backlog_summary(NANODATA_ROOT),
        "ranked": _to_jsonable(ranked_by_kind),
    }


# --- extra: dictionary lookup / propose (harmonization support) ------------

@mcp.tool()
def dictionary_lookup(kind: str, raw: str) -> dict:
    """Check whether `raw` (a raw endpoint/parameter/unit string) already
    has an entry in the dictionary that governs undefined_reports.py's
    `kind` ("endpoints", "protocol_parameters",
    "protocol_parameter_values", or "units"), applying the same key
    normalization AMBIT applies at import time.

    Returns the mapped value if found, else null (meaning it would show
    up in a project's undefined_*.properties report).
    """
    resolved = di.dictionary_for_kind(NANODATA_ROOT, kind)
    if resolved is None:
        return {
            "error": f"No single dictionary is associated with kind={kind!r}"
        }
    name, dictionary = resolved
    return {"dictionary": name, "mapped_value": di.lookup(dictionary, raw)}


@mcp.tool()
def propose_dictionary_entry(
    kind: str, raw: str, canonical: str, in_annotation: bool | None = None
) -> dict:
    """Append one raw=canonical mapping to the dictionary governing
    `kind` and rewrite the file.

    This is a real write to a shared, version-controlled dictionary --
    review it as a normal git diff before committing, same as any other
    source change; nothing here commits to git. `in_annotation` defaults
    to whether `kind`'s dictionary lives under nanodata-common's
    annotation/ folder (endpoints, protocol_parameters,
    protocol_parameter_values) vs. the nanodata/ folder (units).
    """
    resolved = di.dictionary_for_kind(NANODATA_ROOT, kind)
    if resolved is None:
        return {
            "error": f"No single dictionary is associated with kind={kind!r}"
        }
    name, _ = resolved
    if in_annotation is None:
        in_annotation = kind != "units"
    di.propose_entry(
        NANODATA_ROOT, name, raw, canonical, in_annotation=in_annotation
    )
    return {
        "dictionary": name,
        "raw": raw,
        "canonical": canonical,
        "written": True,
    }


# --- extra: metaenm live-index search (harmonization support) --------------

@mcp.tool()
def search_metaenm(
    query: str, field: str | None = None, limit: int = 20
) -> dict:
    """Search the live metaenm Solr metadata index for endpoint/method/
    parameter-name values actually in use, near `query`.

    Distinct from dictionary_lookup/backlog_report (which check the
    import-time dictionaries and their gaps): this shows what's already
    live across every project's exported data, useful for judging a
    harmonization target (e.g. is "COMET" already indexed, under what
    exact casing/variant). `field` restricts to one of
    metaenm_search.HARMONIZATION_FIELDS; omit to search all of them. Note
    effectendpoint_ss values are composite "ENDPOINT (unit)" strings, not
    the bare endpoint form used in endpoint.properties.

    Requires metaenm_solr_url in env.yaml and ENM_USER / ENM_PWD
    environment variables (same account used by pipelines/metadata).
    """
    if not METAENM_SOLR_URL:
        return {
            "error": "metaenm_solr_url is not configured in env.yaml "
            "(see env_example.yaml)."
        }
    user = os.environ.get("ENM_USER")
    password = os.environ.get("ENM_PWD")
    if not user or not password:
        return {
            "error": "ENM_USER / ENM_PWD environment variables are not set."
        }
    if field is not None:
        results = [
            ms.search_field_terms(
                METAENM_SOLR_URL, user, password, field, query, limit=limit
            )
        ]
    else:
        results = ms.search_harmonization_terms(
            METAENM_SOLR_URL, user, password, query, limit=limit
        )
    return {"results": _to_jsonable(results)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
