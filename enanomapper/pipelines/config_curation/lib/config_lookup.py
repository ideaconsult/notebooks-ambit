"""Find whether an Excel file (optionally a sheet) already has a mapping
line in some `projectdata-<project>/.../*.properties` driver file.

These driver `.properties` files (documented in nanodata/AGENTS.md) are a
different format from the `<PREFIX>-undefined_*.properties` reports
undefined_reports.py reads: each non-comment line pairs an Excel path
(optionally `#<sheet-index>`) with a JSON config filename, e.g.

    /nanodata-gracious/casestudies/pigments/Pigments4import.xlsx#1=pchem.json

A line starting with `#` in front of a `/nanodata-...` path is a *disabled*
mapping (the Excel exists but its import is switched off) -- that's a
different, meaningful state from "no line at all" (never configured), so
this module parses raw text rather than reusing javaprops.load() (which
discards comment lines entirely and would conflate the two states).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A driver-properties data line: optional leading '#' (disabled), then a
# '/nanodata-<project>/...' path, optional '#<sheet>', '=', then the config
# filename. Excel paths may contain backslash-escaped spaces.
_LINE_RE = re.compile(
    r"^(?P<disabled>#)?"
    r"(?P<excel>/nanodata-[^=]+?\.xlsx?)"
    r"(?:#(?P<sheet>\d+))?"
    r"=(?P<config>\S+)\s*$"
)


@dataclass(frozen=True)
class ConfigReference:
    properties_file: Path
    line_no: int
    excel_path: str       # as written, e.g. "/nanodata-gracious/.../file.xlsx"
    sheet: int | None      # 1-based sheet index, or None if unspecified
    config_file: str       # RHS, e.g. "pchem.json"
    disabled: bool         # True if the line is commented out


def find_driver_properties_files(
    nanodata_root: Path, project: str | None = None
) -> list[Path]:
    """All driver `.properties` files under projectdata-*/src/main/resources.

    These are distinct from the `<PREFIX>-undefined_*.properties` reports
    (which live directly in the module root, not under src/...).
    """
    if project:
        roots = [nanodata_root / f"projectdata-{project}"]
    else:
        roots = sorted(nanodata_root.glob("projectdata-*"))
    files = []
    for root in roots:
        files.extend(sorted(root.glob("src/main/resources/**/*.properties")))
    return files


def _unescape_path(s: str) -> str:
    return s.replace("\\ ", " ")


def parse_driver_properties(path: Path) -> list[ConfigReference]:
    """Parse every Excel-mapping line (active/disabled) in one driver file."""
    refs = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, raw_line in enumerate(lines, start=1):
        m = _LINE_RE.match(raw_line.strip())
        if not m:
            continue
        refs.append(
            ConfigReference(
                properties_file=path,
                line_no=i,
                excel_path=_unescape_path(m.group("excel")),
                sheet=int(m.group("sheet")) if m.group("sheet") else None,
                config_file=m.group("config"),
                disabled=m.group("disabled") is not None,
            )
        )
    return refs


@dataclass(frozen=True)
class FindConfigResult:
    status: str  # "active" | "disabled" | "not_found"
    matches: tuple[ConfigReference, ...]


def find_config(
    nanodata_root: Path,
    excel_path: str,
    sheet: int | None = None,
    *,
    project: str | None = None,
) -> FindConfigResult:
    """Locate the driver-properties line(s) referencing `excel_path`.

    `excel_path` is matched by filename (the driver line's RHS path and the
    caller's path may be expressed relative to different roots), optionally
    narrowed to one `sheet`. Status is "active" if at least one matching
    line is enabled, "disabled" if all matches are commented out, and
    "not_found" if the Excel file has no driver-properties line at all --
    the three cases nanodata/AGENTS.md documents as "spotting missing
    configs".
    """
    target_name = Path(excel_path).name

    all_matches = []
    for props_file in find_driver_properties_files(nanodata_root, project):
        for ref in parse_driver_properties(props_file):
            if Path(ref.excel_path).name != target_name:
                continue
            if sheet is not None and ref.sheet != sheet:
                continue
            all_matches.append(ref)

    if not all_matches:
        return FindConfigResult(status="not_found", matches=())
    if any(not m.disabled for m in all_matches):
        return FindConfigResult(status="active", matches=tuple(all_matches))
    return FindConfigResult(status="disabled", matches=tuple(all_matches))
