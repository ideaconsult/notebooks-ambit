"""Shape-validate AMBIT JSON with pyambit (charisma/pyambit-main).

Applies to native AMBIT JSON only -- i.e. the output of
`enmconvertor -c data -O json` (nmdataparser) or the live AMBIT REST API,
shaped {"records": N, "substance": [...]} with SubstanceRecord fields
like `name`, `study`, `composition` (verified against
charisma/pyambit-main/tests/pyambit/resources/substance.json).

Does NOT apply to anything under nanodata/sql/<project>/export_json/ --
those files are Solr-indexed JSON (dynamic-field-suffixed keys like
`name_hs`, `content_hss`, `_childDocuments_`), a different, later-stage
shape produced by importing AMBIT JSON into Solr. Validating a Solr
export with Substances(**data) will fail with "Field required: name"
style errors for every record -- that is not a bug in the config, it
just means the wrong file was checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyambit.datamodel import Substances


@dataclass
class ValidationResult:
    valid: bool
    substance_count: int = 0
    error: str | None = None


def validate_file(json_path: Path) -> ValidationResult:
    """Load and shape-validate one AMBIT JSON file.

    Returns valid=True with substance_count set on success; valid=False
    with the Pydantic error message (truncated) on failure. Never raises
    -- callers (MCP tool included) can present the result directly.
    """
    import json

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return ValidationResult(valid=False, error=f"{type(e).__name__}: {e}")

    if isinstance(data, list):
        # Bare list of substance dicts (no {"records", "substance"}
        # envelope) -- accept it the same way, since some producers
        # emit this shape.
        data = {"substance": data}

    try:
        s = Substances(**data)
    except Exception as e:  # pydantic.ValidationError, primarily
        msg = str(e)
        return ValidationResult(
            valid=False,
            error=msg if len(msg) < 2000 else msg[:2000] + " …(truncated)",
        )
    return ValidationResult(valid=True, substance_count=len(s.substance))
