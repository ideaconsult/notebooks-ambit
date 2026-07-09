"""Read/write access to the nanodata-common harmonization dictionaries.

Two folders hold Java .properties dictionaries, both under
nanodata/nanodata-common/src/main/resources/net/idea/:

- annotation/  -- raw term -> ontology PURL / AMBIT EP_* code, reloaded
  server-side by ambit-git's AbstractAnnotator (and subclasses
  SubstanceRecordAnnotationProcessor, FacetAnnotator) to populate the
  *_synonym_ss Solr fields at export/index time. Includes: assays,
  cells, conditions, endpoint, endpointcategory, guideline, medium,
  params, species, substance.
- nanodata/  -- a mix of raw->normalized-string lookups (units,
  ownernames, substancename) and cross-template/cross-project code
  translation tables (JRC2ENM, nmcode2jrcid, parameters_enm2nanoreg,
  parameters_marina2enm, protocol, values) -- NOT all of these are
  "harmonization" dictionaries in the endpoint/parameter/unit sense; the
  caller picks the relevant file by name.

A raw value with no entry in the relevant annotation/*.properties
dictionary is exactly what ends up in a project's
<PREFIX>-undefined_<kind>.properties report (see undefined_reports.py) --
this module is how a harmonization tool reads those dictionaries and
proposes/writes new entries to close that gap.
"""

from __future__ import annotations

from pathlib import Path

from . import javaprops

# undefined_reports.py kind -> the annotation/*.properties dictionary that
# a lookup miss for that kind actually falls back to.
KIND_TO_DICTIONARY = {
    "endpoints": "endpoint",
    "protocol_parameters": "params",
    "protocol_parameter_values": "params",
    "units": None,  # unit harmonization uses nanodata/units.properties,
                    # not annotation/
}


def annotation_dir(nanodata_root: Path) -> Path:
    return (
        nanodata_root
        / "nanodata-common" / "src" / "main" / "resources"
        / "net" / "idea" / "annotation"
    )


def nanodata_dict_dir(nanodata_root: Path) -> Path:
    return (
        nanodata_root
        / "nanodata-common" / "src" / "main" / "resources"
        / "net" / "idea" / "nanodata"
    )


def list_annotation_dictionaries(nanodata_root: Path) -> list[str]:
    """Names (without .properties) of the annotation/*.properties files."""
    return sorted(
        p.stem for p in annotation_dir(nanodata_root).glob("*.properties")
    )


def list_nanodata_dictionaries(nanodata_root: Path) -> list[str]:
    """Names (without .properties) of the nanodata/*.properties files."""
    return sorted(
        p.stem for p in nanodata_dict_dir(nanodata_root).glob("*.properties")
    )


def _normalize_key(raw: str) -> str:
    """Mirror the key normalization AMBIT's AbstractAnnotator applies.

    Confirmed from real dictionary entries (e.g. endpoint.properties:
    ASPECT_RATIO=..., not "Aspect Ratio="): keys are uppercased with
    spaces collapsed to underscores.
    """
    return raw.strip().upper().replace(" ", "_")


def load_annotation(nanodata_root: Path, name: str) -> dict[str, str]:
    """Load one annotation/<name>.properties dictionary.

    Returns the raw dict as stored (key case as written in the file --
    use lookup() for a normalized-key check).
    """
    return javaprops.load(annotation_dir(nanodata_root) / f"{name}.properties")


def load_nanodata_dict(nanodata_root: Path, name: str) -> dict[str, str]:
    """Load one nanodata/<name>.properties file."""
    path = nanodata_dict_dir(nanodata_root) / f"{name}.properties"
    return javaprops.load(path)


def lookup(dictionary: dict[str, str], raw: str) -> str | None:
    """Check whether `raw` (as it would appear in a spreadsheet/config)
    already has a dictionary entry, applying the same key normalization
    AMBIT applies at import/export time. Returns the mapped value, or
    None if genuinely undefined (i.e. would show up in an
    undefined_*.properties report).
    """
    normalized = _normalize_key(raw)
    if normalized in dictionary:
        return dictionary[normalized]
    # dictionaries are not perfectly normalized either (e.g. some
    # annotation/*.properties keys keep original casing) -- also try an
    # exact and a case-insensitive match against the raw keys actually
    # present.
    if raw in dictionary:
        return dictionary[raw]
    raw_lower = raw.strip().lower()
    for k, v in dictionary.items():
        if k.strip().lower() == raw_lower:
            return v
    return None


def dictionary_for_kind(
    nanodata_root: Path, kind: str
) -> tuple[str, dict[str, str]] | None:
    """The (name, dict) pair an undefined_reports.py `kind` should be
    checked/harmonized against, or None if there is no single obvious
    dictionary for that kind (see KIND_TO_DICTIONARY).
    """
    if kind == "units":
        return "units", load_nanodata_dict(nanodata_root, "units")
    name = KIND_TO_DICTIONARY.get(kind)
    if name is None:
        return None
    return name, load_annotation(nanodata_root, name)


def propose_entry(
    nanodata_root: Path,
    name: str,
    raw: str,
    canonical: str,
    *,
    in_annotation: bool,
) -> None:
    """Append one raw=canonical mapping to a dictionary file and rewrite it.

    This is a real write to a shared, version-controlled dictionary --
    callers (the MCP tool / a Claude Code session) must treat every call
    as something the human reviews as a normal git diff before it is
    committed, exactly like any other source change. Nothing in this
    module commits to git.
    """
    base_dir = (
        annotation_dir(nanodata_root)
        if in_annotation
        else nanodata_dict_dir(nanodata_root)
    )
    path = base_dir / f"{name}.properties"
    data = javaprops.load(path)
    key = _normalize_key(raw) if in_annotation else raw
    data[key] = canonical
    javaprops.dump(path, data)
