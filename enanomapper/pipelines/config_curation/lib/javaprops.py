"""Minimal Java .properties reader/writer.

The nanodata/nanodata-common dictionaries and the per-project
``<PREFIX>-undefined_<type>.properties`` reports are written by
``java.util.Properties.store()`` (see AbstractImportTest.storeUndefined
in ambit-git). That format backslash-escapes spaces and a handful of
special characters and writes UTF-8. No existing Python dependency in
this repo set reads it, so this is a small, self-contained
implementation rather than a new package dependency.
"""

from __future__ import annotations

from pathlib import Path

_ESCAPES = {
    "\\ ": " ",
    "\\:": ":",
    "\\=": "=",
    "\\#": "#",
    "\\!": "!",
    "\\\\": "\\",
    "\\t": "\t",
    "\\n": "\n",
    "\\r": "\r",
}


def _unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            pair = s[i : i + 2]
            if pair == "\\u" and i + 6 <= len(s):
                out.append(chr(int(s[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(_ESCAPES.get(pair, pair[1]))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _escape_key(s: str) -> str:
    out = []
    for c in s:
        if c == " ":
            out.append("\\ ")
        elif c in ":=#!\\":
            out.append("\\" + c)
        else:
            out.append(c)
    return "".join(out)


def load(path: Path) -> dict[str, str]:
    """Parse a Java .properties file into an ordered dict.

    Comment lines (# or !) and the timestamp line
    java.util.Properties.store() always emits are skipped. Continuation
    lines (trailing backslash) are joined.
    """
    text = path.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    pending = ""
    for raw_line in text.splitlines():
        line = pending + raw_line
        pending = ""
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("!")
        ):
            continue
        if line.endswith("\\") and not line.endswith("\\\\"):
            pending = line[:-1]
            continue
        # First unescaped '=' or ':' separates key/value (properties also
        # allows plain whitespace as a separator, but every file in this
        # codebase uses '=').
        idx = None
        i = 0
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] in "=:":
                idx = i
                break
            i += 1
        if idx is None:
            key, value = line, ""
        else:
            key, value = line[:idx], line[idx + 1 :]
        result[_unescape(key.strip())] = _unescape(value.strip())
    return result


def dump(path: Path, data: dict[str, str], comment: str = "") -> None:
    """Write a dict back out in java.util.Properties.store() format."""
    lines = []
    if comment:
        lines.append(f"#{comment}")
    for key, value in data.items():
        lines.append(f"{_escape_key(key)}={_escape_key(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
