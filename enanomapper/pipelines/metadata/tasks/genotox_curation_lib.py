# Shared AMBIT fetch/parse/plot machinery for the genotox curation tasks
# (curate_failing.py, curate_passing.py). Not a Ploomber task — a plain importable module.
#
# Extracted from curate_failing.py so both the failing-studies and passing-studies dashboards
# use the exact same server resolution, fetch, dose-axis selection, and dose-response
# flattening logic — only the study selection filter and summary tables differ per task.

import sys

# Use the clean pyambit-main checkout (the editable `pyambit` install has an unresolved merge
# conflict in datamodel.py).
sys.path.insert(0, "d:/nina/src/charisma/pyambit-main/src")

import ast
import os

import numpy as np
import pandas as pd
import requests

from pyambit.datamodel import Study
from pyambit import study_config as sc


def parse_csv_list(val):
    """Parse a list-valued cell that round-tripped through CSV.

    pandas writes list columns as their Python repr (e.g. "['K562']"), and reading the CSV
    back gives that repr AS A STRING, not a list — so plain `isinstance(val, list)` checks
    silently fail after a CSV round trip (the whole "['K562']" string gets treated as one
    value instead of being unpacked). Always route E.cell_type_ss (and similar list columns)
    read from a CSV through this helper before checking isinstance(..., list).
    """
    if isinstance(val, list):
        return val
    if pd.isna(val):
        return []
    if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
        try:
            parsed = ast.literal_eval(val)
            return parsed if isinstance(parsed, list) else [parsed]
        except (ValueError, SyntaxError):
            return [val]
    return [val]

GENOTOX_INVITRO = "TO_GENETIC_IN_VITRO_SECTION"
VIABILITY = "ENM_0000068_SECTION"  # Cell Viability

# In-study cytotoxicity / proliferation endpoints — the concurrent cytotoxicity control that a
# genotox study carries ON ITSELF (CBPI for CBMN; RI/RPD/RICC/plating/viability). Kept in sync
# with viz_metadata.py's INSTUDY_CYTOTOX_* markers so the c_viab flag and this dashboard's
# right-hand "Cell viability" panel agree: viz_metadata decides the flag, here we PLOT the same
# in-study endpoint. Long phrases matched as substrings; short acronyms (RI/RICC/RPD) matched
# on \b word boundaries so they don't match inside other words and GENOTOXICITY never matches.
INSTUDY_CYTOTOX_SUBSTRING_MARKERS = (
    "CBPI",
    "PROLIFERATION_INDEX",
    "CELL_COUNT_FOR_CBPI",
    "REPLICATION_INDEX",
    "RELATIVE_POPULATION_DOUBLING",
    "RELATIVE_INCREASE_IN_CELL_COUNT",
    "CELL_VIABILITY",
    "CELL_VIABILTIY",              # observed misspelling in the live index
    "PERCENTAGE_VIABILITY",
    "VIABILITY_COMPARED_TO_CONTROL",
    "PLATING_EFFICIENCY",
    "CYTOTOXICITY",
)
INSTUDY_CYTOTOX_WORD_MARKERS = ("RI", "RICC", "RPD")
import re as _re
_INSTUDY_WORD_RE = _re.compile(
    r"\b(" + "|".join(_re.escape(m) for m in INSTUDY_CYTOTOX_WORD_MARKERS) + r")\b"
)


def is_cytotox_endpoint(endpoint):
    """True if an effect endpoint name is an in-study cytotoxicity/proliferation readout
    (CBPI, RI, viability, ...) — used to split a genotox study's own dose-response rows into a
    genotox part (left panel) and an in-study viability part (right panel)."""
    if endpoint is None or (isinstance(endpoint, float) and pd.isna(endpoint)):
        return False
    ep = str(endpoint).upper()
    if any(marker in ep for marker in INSTUDY_CYTOTOX_SUBSTRING_MARKERS):
        return True
    return bool(_INSTUDY_WORD_RE.search(ep))

# --- AMBIT server resolution (ported from spectrasearch-viewers/src/utils/tagdbs.js) ---------
# 4-letter tag = prefix before the first "-" in s_uuid_s -> AMBIT server base URL.
TAG_DBS_AMBIT = {
    "ENM":  "https://data.enanomapper.net/",
    "NNRG": "https://apps.ideaconsult.net/nanoreg1/",
    "NRGF": "https://apps.ideaconsult.net/nanoreg1/",
    "NRTR": "https://apps.ideaconsult.net/nanoreg1/",
    "MRNA": "https://apps.ideaconsult.net/marina/",
    "NTST": "https://apps.ideaconsult.net/nanotest/",
    "NGTX": "https://apps.ideaconsult.net/nanogenotox/",
    "ENPR": "https://apps.ideaconsult.net/enpra/",
    "GRCS": "https://apps.ideaconsult.net/gracious/",
    "PGMS": "https://apps.ideaconsult.net/gracious_pigments/",
    "CLBR": "https://apps.ideaconsult.net/calibrate/",
    "NRG2": "https://apps.ideaconsult.net/nanoreg2/",
    "NOMX": "https://apps.ideaconsult.net/nanoomics/",
    "SNWK": "https://apps.ideaconsult.net/sanowork/",
    "RGNE": "https://apps.ideaconsult.net/riskgone/",
    "CNLB": "https://apps.ideaconsult.net/marina/",
    "NGRV": "https://apps.ideaconsult.net/gracious/",
    "NOSH": "https://apps.ideaconsult.net/nanoinformatix/",
    "NTIX": "https://apps.ideaconsult.net/nanoinformatix/",
    "AMBT": "https://ambitlri.ideaconsult.net/tool2/",
    "SBDN": "https://apps.ideaconsult.net/sbd4nano/",
    "SBMA": "https://apps.ideaconsult.net/sabydoma/",
    "HRMZ": "https://apps.ideaconsult.net/harmless/",
    "PATS": "https://apps.ideaconsult.net/patrols/",
    "CRMA": "https://apps.ideaconsult.net/charisma/",
    "POLY": "https://apps.ideaconsult.net/polyrisk/",
    "PLFT": "https://apps.ideaconsult.net/plasticfate/",
    "HEAL": "https://apps.ideaconsult.net/plasticheal/",
    "IUC6": "https://apps.ideaconsult.net/tool3/",
    "ZROF": "https://apps.ideaconsult.net/zerof/",
}

TAG_DBS = {
    "ENM":  "https://data.enanomapper.net/",
    "NNRG": "https://apps.ideaconsult.net/nanoreg1/",
    "NRGF": "https://apps.ideaconsult.net/nanoreg1/",
    "NRTR": "https://apps.ideaconsult.net/nanoreg1/",
    "MRNA": "https://apps.ideaconsult.net/marina/",
    "NTST": "https://apps.ideaconsult.net/nanotest/",
    "NGTX": "https://apps.ideaconsult.net/nanogenotox/",
    "ENPR": "https://apps.ideaconsult.net/enpra/",
    "GRCS": "https://apps.ideaconsult.net/gracious/",
    "PGMS": "https://apps.ideaconsult.net/gracious_pigments/",
    "CLBR": "https://apps.ideaconsult.net/calibrate/",
    "NRG2": "https://api.ideaconsult.net/nanoreg2/enm/nanoreg2/",
    "NOMX": "https://apps.ideaconsult.net/nanoomics/",
    "SNWK": "https://apps.ideaconsult.net/sanowork/",
    "RGNE": "https://api.ideaconsult.net/riskgone/enm/riskgone/",
    "CNLB": "https://apps.ideaconsult.net/marina/",
    "NGRV": "https://apps.ideaconsult.net/gracious/",
    "NOSH": "https://apps.ideaconsult.net/nanoinformatix/",
    "NTIX": "https://apps.ideaconsult.net/nanoinformatix/",
    "AMBT": "https://ambitlri.ideaconsult.net/tool2/",
    "SBDN": "https://apps.ideaconsult.net/sbd4nano/",
    "SBMA": "https://apps.ideaconsult.net/sabydoma/",
    "HRMZ": "https://api.ideaconsult.net/harmless/enm/harmless/",
    "PATS": "https://apps.ideaconsult.net/patrols/",
    "CRMA": "https://apps.ideaconsult.net/charisma/",
    "POLY": "https://apps.ideaconsult.net/polyrisk/",
    "PLFT": "https://apps.ideaconsult.net/plasticfate/",
    "HEAL": "https://apps.ideaconsult.net/plasticheal/",
    "IUC6": "https://apps.ideaconsult.net/tool3/",
    "ZROF": "https://apps.ideaconsult.net/zerof/",
}

def substance2server(s_uuid):
    """4-letter tag (prefix before first '-') -> AMBIT/Gravitee fetch server, or None if
    unknown. Used for actual data retrieval — may be a Gravitee API gateway URL
    (api.ideaconsult.net/{project}/enm/{project}/) which is NOT a browsable UI page."""
    if not s_uuid:
        return None
    tag = s_uuid.split("-")[0] if "-" in s_uuid else s_uuid
    
    return TAG_DBS.get(tag)


def substance2ui_url(s_uuid):
    """Browsable AMBIT substance page URL (apps.ideaconsult.net), for human-facing links.

    Distinct from substance2server(): TAG_DBS may point some tags at the Gravitee API
    gateway for fetching (api.ideaconsult.net/.../enm/...), which returns JSON, not a
    renderable page. Links a curator clicks should always go to the real UI server.
    """
    if not s_uuid:
        return None
    tag = s_uuid.split("-")[0] if "-" in s_uuid else s_uuid
    return TAG_DBS_AMBIT.get(tag)


# --- Gravitee auth (per-project API keys) -------------------------------------------------
# The Gravitee gateway (api.ideaconsult.net) requires an X-Gravitee-Api-Key header, but each
# project has its OWN subscription key — there is no single shared key. Map tag -> the env
# var name holding that project's key, so each is set only if/when the user has it.
GRAVITEE_KEY_ENV = {
    "NRG2": "GRAVITEE_API_KEY_NRG2",
    "RGNE": "GRAVITEE_API_KEY_RGNE",
    "HRMZ": "GRAVITEE_API_KEY_HRMZ",
}


def _gravitee_auth_for_tag(tag):
    """GraviteeAuth for `tag`'s project key (from its env var), or None if not set / not a
    Gravitee-fronted tag — fetch_studies then makes an unauthenticated request as before."""
    env_name = GRAVITEE_KEY_ENV.get(tag)
    if not env_name:
        return None
    key = os.environ.get(env_name)
    if not key:
        return None
    from pynanomapper import aa
    return aa.GraviteeAuth(apikey=key)


def fetch_studies(server, s_uuid, category=GENOTOX_INVITRO):
    """Fetch a substance's studies from AMBIT, restricted to one endpoint category.

    Attaches the project-specific X-Gravitee-Api-Key header (from that project's
    GRAVITEE_API_KEY_<TAG> env var, see GRAVITEE_KEY_ENV) when `server` is Gravitee-fronted
    and a key is available; otherwise the request is unauthenticated, same as before.

    Returns (list_of_ProtocolApplication, reason) — reason is None on success, else a short
    string ('unknown server tag', 'HTTP 403', 'not JSON', 'error: ...') for the skip list.
    """
    tag = s_uuid.split("-")[0] if s_uuid and "-" in s_uuid else s_uuid
    url = "{}/substance/{}/study".format(server.rstrip("/"), s_uuid)
    try:
        r = requests.get(
            url,
            params={"media": "application/json", "top": "TOX", "category": category},
            auth=_gravitee_auth_for_tag(tag),
            timeout=120,
        )
    except Exception as err:
        return [], "error: {}".format(err)
    if r.status_code != 200:
        return [], "HTTP {}".format(r.status_code)
    if "json" not in r.headers.get("content-type", ""):
        return [], "not JSON (protected?)"
    try:
        papps = Study.model_construct(**r.json())
    except Exception as err:
        return [], "parse error: {}".format(err)
    return list(papps.study or []), None


# kept for backwards compatibility with existing callers (curate_failing.py)
def fetch_genotox_studies(server, s_uuid):
    return fetch_studies(server, s_uuid, category=GENOTOX_INVITRO)


# --- dose-axis selection (config-driven, NOT hardcoded) -------------------------------------
# study_config tells us which condition key is the dose axis for this category. The AMBIT
# EffectArray axis names are upper-cased (CONCENTRATION), the config keys are lower-case
# (concentration), so match case-insensitively.
_DOSE_KEYS_UP = {k.upper() for k in sc.dose_condition_fields(GENOTOX_INVITRO)}


def pick_dose_axis(axes):
    """Return the name of the dose axis among an EffectArray's axes, or None."""
    if not axes:
        return None
    for name in axes:
        if name.upper() in _DOSE_KEYS_UP or name.upper().startswith("CONCENTRATION"):
            return name
    return None


def study_to_long_rows(papp, meta):
    """Flatten one study's resolved EffectArrays to long dose/response rows.

    Uses ProtocolApplication.convert_effectrecords2array() — the same machinery pyambit uses
    to build the dose axis + signal, so we don't guess columns. Returns a list of dicts, each
    one (dose, response) point for one endpoint.
    """
    try:
        arrays, _ = papp.convert_effectrecords2array()
    except Exception as err:
        print("  convert failed for", papp.uuid, err)
        return []
    rows = []
    for ea in arrays:
        if ea.signal is None or ea.signal.values is None or not ea.axes:
            continue
        dose_name = pick_dose_axis(ea.axes)
        if dose_name is None:
            continue
        dose_vals = np.asarray(ea.axes[dose_name].values).ravel()
        signal = np.asarray(ea.signal.values)
        # signal is (len(other_axes) x len(dose)) — collapse to the dose dimension
        if signal.ndim > 1:
            # pick the axis whose length matches the dose vector
            axis = next((i for i, s in enumerate(signal.shape) if s == len(dose_vals)), -1)
            signal = np.nanmean(signal, axis=tuple(j for j in range(signal.ndim) if j != axis)) \
                if axis >= 0 else signal.ravel()
        signal = np.asarray(signal).ravel()
        n = min(len(dose_vals), len(signal))
        for i in range(n):
            # a non-numeric value on the dose axis (e.g. b'C-'/b'C+') means this row IS a
            # control, not a concentration point — keep the label, leave dose empty rather
            # than crash or silently drop the point.
            raw = dose_vals[i]
            dose, control_label = None, None
            try:
                dose = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                control_label = raw.decode() if isinstance(raw, bytes) else str(raw)
            rows.append({
                **meta,
                "endpoint": ea.endpoint,
                "dose_axis": dose_name,
                "dose": dose,
                "control_label": control_label,
                "dose_unit": ea.axes[dose_name].unit,
                "response": float(signal[i]) if signal[i] is not None else None,
                "response_unit": ea.signal.unit,
            })
    return rows


# --- positive/negative control evidence from PARAMETERS, not just conditions ----------------
# viz_metadata.py already widens has_positive_control_b / has_negative_control_b with param
# evidence (param_E.POSITIVE_CONTROLID_t etc.) for the readiness flags. Here we go one step
# further and PLOT the control's identity/concentration when it's only recorded as a
# parameter — e.g. E.POSITIVE_CONTROLID: "Ethyl methanesulfonate",
# E.POSITIVE_CONTROL_CONCENTRATION: "3.7 mg/ml" — so the curator can see it, not just know it
# exists.
POS_PARAM_KEYS = ("E.POSITIVE_CONTROLID", "E.POSITIVE_CONTROL")
POS_CONC_KEY = "E.POSITIVE_CONTROL_CONCENTRATION"
NEG_PARAM_KEYS = ("E.NEGATIVE_CONTROLID", "E.NEGATIVE_CONTROL")
NEG_CONC_KEY = "E.NEGATIVE_CONTROL_CONCENTRATION"


def _param_str(val):
    """papp.parameters values are either a plain string or a pyambit Value object."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    lo = getattr(val, "loValue", None)
    unit = getattr(val, "unit", None)
    if lo is not None:
        return "{} {}".format(lo, unit).strip() if unit else str(lo)
    return str(val)


def param_control_rows(papp, min_dose):
    """Positive/negative control points sourced from parameters (not the dose axis)."""
    params = papp.parameters or {}
    rows = []
    for keys, conc_key, kind in ((POS_PARAM_KEYS, POS_CONC_KEY, "positive control (param)"),
                                 (NEG_PARAM_KEYS, NEG_CONC_KEY, "negative control (param)")):
        identity = next((_param_str(params[k]) for k in keys if params.get(k) is not None), None)
        if identity is None:
            continue
        conc_raw = _param_str(params.get(conc_key))
        dose = None
        if conc_raw:
            try:
                dose = float(conc_raw.split()[0])
            except (ValueError, IndexError):
                dose = None
        rows.append({
            "endpoint": None, "dose_axis": None,
            "dose": dose if dose is not None else min_dose,
            "control_label": "{}: {}{}".format(
                kind, identity, " ({})".format(conc_raw) if conc_raw else ""),
            "dose_unit": None, "response": None, "response_unit": None,
        })
    return rows


def esc(s):
    """HTML-escape a value for safe embedding in a table cell."""
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;")


def fetch_and_flatten(sel, failing_by_substance, label_by_doc, extra_meta_fn,
                       category=GENOTOX_INVITRO, add_param_controls=True):
    """Fetch AMBIT data for every (substance, wanted document_uuids) pair and flatten to a
    long dose-response DataFrame.

    sel: the filtered readiness rows (DataFrame), one row per document_uuid_s.
    failing_by_substance: {s_uuid_s: set(document_uuid_s)} — despite the name (kept for
        continuity with curate_failing.py), this is just "selected studies grouped by
        substance" — used for failing, passing, AND viability lookups.
    label_by_doc: {document_uuid_s: label string} for the plot/table.
    extra_meta_fn(row) -> dict: per-study extra metadata merged into `meta` (e.g. "fails" for
        curate_failing, "assay"/"studyResultType_s" for curate_passing).
    category: AMBIT endpointcategory_s to restrict the study fetch to (genotox by default;
        pass VIABILITY to fetch cell-viability studies for the same substances instead).
    add_param_controls: whether to also emit parameter-sourced control points (only
        meaningful for genotox — viability studies don't carry POSITIVE/NEGATIVE_CONTROLID).

    Returns (data: DataFrame, not_retrieved: list[dict]).
    """
    long_rows = []
    not_retrieved = []

    for s_uuid, wanted in failing_by_substance.items():
        server = substance2server(s_uuid)
        owner = sel.loc[sel["s_uuid_s"] == s_uuid, "owner_name_s"].iloc[0]
        if server is None:
            for doc in wanted:
                not_retrieved.append({"document_uuid_s": doc, "s_uuid_s": s_uuid,
                                      "owner_name_s": owner, "reason": "unknown server tag"})
            continue

        studies, reason = fetch_studies(server, s_uuid, category=category)
        if reason is not None:
            for doc in wanted:
                not_retrieved.append({"document_uuid_s": doc, "s_uuid_s": s_uuid,
                                      "owner_name_s": owner, "reason": reason})
            continue

        fetched_uuids = {p.uuid for p in studies}
        for papp in studies:
            if papp.uuid not in wanted:
                continue
            row = sel.loc[sel["document_uuid_s"] == papp.uuid].iloc[0]
            meta = {
                "document_uuid_s": papp.uuid,
                "s_uuid_s": s_uuid,
                "owner_name_s": owner,
                "publicname_s": row.get("publicname_s"),
                "input_file": row.get("param___input_file_t"),
                "label": label_by_doc.get(papp.uuid, papp.uuid),
                # human-facing link: always the browsable apps.ideaconsult.net UI, never the
                # Gravitee fetch server (which returns JSON, not a renderable page).
                "substance_url": "{}/substance/{}".format(
                    (substance2ui_url(s_uuid) or server).rstrip("/"), s_uuid),
                "study_url": "{}/substance/{}/study?media=application/json&category={}"
                             .format(server.rstrip("/"), s_uuid, category),
                **extra_meta_fn(row),
            }
            study_rows = study_to_long_rows(papp, meta)
            if study_rows:
                long_rows.extend(study_rows)
                if add_param_controls:
                    study_doses = [r["dose"] for r in study_rows if r["dose"] is not None]
                    study_min_dose = min(study_doses) if study_doses else 1.0
                    long_rows.extend({**meta, **r}
                                     for r in param_control_rows(papp, study_min_dose))
            else:
                not_retrieved.append({"document_uuid_s": papp.uuid, "s_uuid_s": s_uuid,
                                      "owner_name_s": owner,
                                      "reason": "retrieved but no dose-response array"})
        for doc in wanted - fetched_uuids:
            not_retrieved.append({"document_uuid_s": doc, "s_uuid_s": s_uuid,
                                  "owner_name_s": owner, "reason": "study not returned by server"})

    return pd.DataFrame(long_rows), not_retrieved


def _papp_cell_type(papp):
    """E.cell_type from an AMBIT ProtocolApplication's parameters (Solr indexes this same
    value as E.cell_type_s). Confirmed present on live viability study JSON."""
    params = papp.parameters or {}
    return _param_str(params.get("E.cell_type") or params.get("E.CELL_TYPE"))


def fetch_paired_viability(sel, by_substance):
    """Fetch each substance's cell-viability studies and pick the best-paired one per genotox
    document_uuid_s — using EXACTLY viz_metadata.py's pairing logic (has_paired_viability),
    so the plotted panel never disagrees with the c_viab flag / "fails" text:
      1. primary: a viability study sharing the genotox study's investigation_uuid_s
      2. fallback: a viability study matching (owner_name_s, s_uuid_s, cell_type) — NOT just
         "any viability study on the substance" (that ignored cell type and could pair a
         genotox study with an unrelated cell line's viability data).

    sel: the filtered readiness rows (DataFrame), one row per genotox document_uuid_s. Needs
        s_uuid_s, owner_name_s, E.cell_type_ss, and (if present) investigation_uuid_s.
    by_substance: {s_uuid_s: set(document_uuid_s)} — the genotox studies grouped by substance
        (same shape as fetch_and_flatten's second argument); only its keys (which substances
        to fetch viability for) are used here.

    Returns (viability_data: DataFrame, viability_doc_by_genotox_doc: dict, not_retrieved: list).
    """
    via_rows = []
    not_retrieved = []
    cell_type_by_via_doc = {}

    for s_uuid in by_substance:
        server = substance2server(s_uuid)
        if server is None:
            not_retrieved.append({"s_uuid_s": s_uuid, "reason": "unknown server tag"})
            continue
        owner_rows = sel.loc[sel["s_uuid_s"] == s_uuid, "owner_name_s"]
        owner = owner_rows.iloc[0] if not owner_rows.empty else None
        via_studies, reason = fetch_studies(server, s_uuid, category=VIABILITY)
        if reason is not None:
            not_retrieved.append({"s_uuid_s": s_uuid, "reason": reason})
            continue
        for papp in via_studies:
            cell_type_by_via_doc[papp.uuid] = _papp_cell_type(papp)
            meta = {
                "document_uuid_s": papp.uuid, "s_uuid_s": s_uuid, "owner_name_s": owner,
                "label": "viability: {}".format(papp.uuid),
                "substance_url": "{}/substance/{}".format(
                    (substance2ui_url(s_uuid) or server).rstrip("/"), s_uuid),
                "study_url": "{}/substance/{}/study?media=application/json&category={}"
                             .format(server.rstrip("/"), s_uuid, VIABILITY),
                "investigation_uuid": papp.investigation_uuid,
            }
            rows = study_to_long_rows(papp, meta)
            if rows:
                via_rows.extend(rows)

    viability_data = pd.DataFrame(via_rows)
    viability_doc_by_genotox_doc = {}
    if not viability_data.empty:
        via_by_inv = (
            viability_data.drop_duplicates("document_uuid_s")
            .set_index("investigation_uuid")["document_uuid_s"].to_dict()
        )
        # (owner_name_s, s_uuid_s, cell_type) -> viability document_uuid_s, mirroring
        # viz_metadata.py's viability_contexts / has_paired_viability exactly.
        via_docs = viability_data.drop_duplicates("document_uuid_s")
        via_by_context = {}
        for _, vr in via_docs.iterrows():
            ct = cell_type_by_via_doc.get(vr["document_uuid_s"])
            key = (str(vr["owner_name_s"]), str(vr["s_uuid_s"]), str(ct) if ct else "?")
            via_by_context.setdefault(key, vr["document_uuid_s"])

        for _, row in sel.iterrows():
            doc = row["document_uuid_s"]
            if row["s_uuid_s"] not in by_substance:
                continue
            inv = row.get("investigation_uuid_s")
            via_doc = via_by_inv.get(inv) if pd.notna(inv) else None
            if via_doc is None:
                owner = str(row["owner_name_s"]) if pd.notna(row.get("owner_name_s")) else "?"
                nm = str(row["s_uuid_s"]) if pd.notna(row.get("s_uuid_s")) else "?"
                cells = parse_csv_list(row.get("E.cell_type_ss")) or ["?"]
                for c in cells:
                    via_doc = via_by_context.get((owner, nm, str(c)))
                    if via_doc:
                        break
            viability_doc_by_genotox_doc[doc] = via_doc

    return viability_data, viability_doc_by_genotox_doc, not_retrieved


def build_dropdown_figure(data, dropdown_label_fn, dropdown_sort_key_fn=None):
    """Build the dropdown-driven dose-response Plotly figure shared by both tasks.

    data: long-format DataFrame (document_uuid_s, label, dose, response, control_label,
        dose_unit, response_unit, endpoint, ...).
    dropdown_label_fn(sdf_first_row) -> str: builds the dropdown button text for one study
        (sdf_first_row is the first row of that study's slice of `data`).
    dropdown_sort_key_fn(doc_id) -> sortable key: controls dropdown ordering (defaults to
        document order).

    Returns the assembled `go.Figure` — NOT yet written to HTML; callers splice their own
    extra HTML sections into `fig.to_html()` themselves.
    """
    import plotly.graph_objects as go

    studies_order = list(dict.fromkeys(data["document_uuid_s"]))
    fig = go.Figure()
    trace_study = []
    min_dose = data["dose"].dropna().min() if data["dose"].notna().any() else 1.0

    for s_idx, doc in enumerate(studies_order):
        sdf = data[data["document_uuid_s"] == doc]
        dose_pts = sdf[sdf["dose"].notna() & sdf["response"].notna()
                      & sdf["control_label"].isna()].sort_values("dose")
        ctrl_pts = sdf[sdf["control_label"].notna()]

        for endpoint, g in dose_pts.groupby("endpoint"):
            fig.add_trace(go.Scatter(
                x=g["dose"], y=g["response"], mode="markers+lines", name=str(endpoint),
                visible=(s_idx == 0),
                hovertemplate=(
                    "endpoint=%{fullData.name}<br>dose=%{x} " + str(g["dose_unit"].iloc[0] or "")
                    + "<br>response=%{y} " + str(g["response_unit"].iloc[0] or "") + "<extra></extra>"
                ),
            ))
            trace_study.append(s_idx)

        for _, row in ctrl_pts.iterrows():
            has_response = pd.notna(row["response"])
            x_val = row["dose"] if pd.notna(row["dose"]) else min_dose
            y_val = row["response"] if has_response else 0
            fig.add_trace(go.Scatter(
                x=[x_val], y=[y_val], mode="markers+text",
                text=[row["control_label"]], textposition="top center",
                marker=dict(symbol="star", size=13,
                           color="black" if has_response else "crimson"),
                name=row["control_label"], visible=(s_idx == 0), showlegend=False,
            ))
            trace_study.append(s_idx)

    select_caption = dict(
        text="<b>Select study</b> (see the table below the plot for UUID / links / details)",
        x=0, xref="paper", y=1.12, yref="paper", showarrow=False, align="left",
    )

    order = sorted(studies_order, key=dropdown_sort_key_fn) if dropdown_sort_key_fn else studies_order
    dropdown_buttons = []
    for doc in order:
        s_idx = studies_order.index(doc)
        sdf = data[data["document_uuid_s"] == doc]
        visible = [ts == s_idx for ts in trace_study]
        dropdown_buttons.append(dict(
            label=dropdown_label_fn(sdf.iloc[0]),
            method="update",
            args=[{"visible": visible}],
        ))

    fig.update_layout(
        title_text=None,
        margin=dict(t=120),
        xaxis=dict(title="dose / concentration", type="log"),
        yaxis=dict(title="effect value"),
        updatemenus=[dict(
            buttons=dropdown_buttons, direction="down",
            x=0, xanchor="left", y=1.05, yanchor="top",
            showactive=True,
        )],
        annotations=[select_caption],
        height=650,
    )
    return fig


def _add_study_traces(fig, sdf, visible0, row=1, col=1):
    """Add one study's dose-response + control traces to `fig` (used by both the single- and
    dual-panel builders). Returns the number of traces added (for trace_study bookkeeping).
    """
    import plotly.graph_objects as go

    n = 0
    dose_pts = sdf[sdf["dose"].notna() & sdf["response"].notna()
                  & sdf["control_label"].isna()].sort_values("dose")
    ctrl_pts = sdf[sdf["control_label"].notna()]
    min_dose = sdf["dose"].dropna().min() if sdf["dose"].notna().any() else 1.0

    for endpoint, g in dose_pts.groupby("endpoint"):
        fig.add_trace(go.Scatter(
            x=g["dose"], y=g["response"], mode="markers+lines", name=str(endpoint),
            visible=visible0,
            hovertemplate=(
                "endpoint=%{fullData.name}<br>dose=%{x} " + str(g["dose_unit"].iloc[0] or "")
                + "<br>response=%{y} " + str(g["response_unit"].iloc[0] or "") + "<extra></extra>"
            ),
        ), row=row, col=col)
        n += 1

    for _, r in ctrl_pts.iterrows():
        has_response = pd.notna(r["response"])
        x_val = r["dose"] if pd.notna(r["dose"]) else min_dose
        y_val = r["response"] if has_response else 0
        fig.add_trace(go.Scatter(
            x=[x_val], y=[y_val], mode="markers+text",
            text=[r["control_label"]], textposition="top center",
            marker=dict(symbol="star", size=13, color="black" if has_response else "crimson"),
            name=r["control_label"], visible=visible0, showlegend=False,
        ), row=row, col=col)
        n += 1

    return n


def build_dual_dropdown_figure(genotox_data, viability_data, viability_doc_by_genotox_doc,
                               dropdown_label_fn, dropdown_sort_key_fn=None):
    """Dropdown-driven figure with TWO panels side by side: genotox dose-response (left) and
    its paired cell-viability dose-response (right), toggled together by one dropdown.

    genotox_data: long-format DataFrame, one or more rows per genotox document_uuid_s.
    viability_data: long-format DataFrame for the fetched viability studies (same shape).
    viability_doc_by_genotox_doc: {genotox_document_uuid_s: viability_document_uuid_s or None}
        — which viability study (if any) is paired with each genotox study.
    dropdown_label_fn(sdf_first_row) -> str: label built from the GENOTOX study's first row.
    dropdown_sort_key_fn(doc_id) -> sortable key for dropdown ordering.

    Returns the assembled `go.Figure`.
    """
    from plotly.subplots import make_subplots

    studies_order = list(dict.fromkeys(genotox_data["document_uuid_s"]))
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Genotox", "Cell viability"))
    trace_study = []

    for s_idx, doc in enumerate(studies_order):
        sdf = genotox_data[genotox_data["document_uuid_s"] == doc]

        # Split the study's OWN rows: genotox endpoints (left) vs. in-study cytotoxicity /
        # proliferation endpoints like CBPI (right). Many NanoTest CBMN studies carry their
        # cytotoxicity control (CBPI) inside the same study rather than as a separate viability
        # study — this surfaces it in the "Cell viability" panel. Control-label rows (no
        # endpoint) stay with the genotox side so the +/- controls still show on the left.
        is_cyto = sdf["endpoint"].apply(is_cytotox_endpoint)
        gsdf = sdf[~is_cyto]
        instudy_via = sdf[is_cyto]

        n = _add_study_traces(fig, gsdf if not gsdf.empty else sdf, s_idx == 0, row=1, col=1)
        trace_study.extend([s_idx] * n)

        # Right panel: in-study cytotoxicity first (same experiment), else a separately-fetched
        # paired viability study. Prefer the in-study data — it is provably the same experiment.
        if not instudy_via.empty:
            n2 = _add_study_traces(fig, instudy_via, s_idx == 0, row=1, col=2)
            trace_study.extend([s_idx] * n2)
        else:
            via_doc = viability_doc_by_genotox_doc.get(doc)
            if via_doc is not None:
                vdf = viability_data[viability_data["document_uuid_s"] == via_doc]
                if not vdf.empty:
                    n2 = _add_study_traces(fig, vdf, s_idx == 0, row=1, col=2)
                    trace_study.extend([s_idx] * n2)
            # no paired viability at all -> right panel empty for this study (valid signal).

    fig.update_xaxes(title_text="dose / concentration", type="log", row=1, col=1)
    fig.update_xaxes(title_text="dose / concentration", type="log", row=1, col=2)
    fig.update_yaxes(title_text="effect value", row=1, col=1)
    fig.update_yaxes(title_text="viability", row=1, col=2)

    select_caption = dict(
        text="<b>Select study</b> (right panel: paired cell-viability — the study's own "
             "in-study cytotoxicity endpoint e.g. CBPI when present, else a separate viability "
             "study; see the table below the plot for UUID / links / details)",
        x=0, xref="paper", y=1.15, yref="paper", showarrow=False, align="left",
    )

    order = sorted(studies_order, key=dropdown_sort_key_fn) if dropdown_sort_key_fn else studies_order
    dropdown_buttons = []
    for doc in order:
        s_idx = studies_order.index(doc)
        sdf = genotox_data[genotox_data["document_uuid_s"] == doc]
        visible = [ts == s_idx for ts in trace_study]
        dropdown_buttons.append(dict(
            label=dropdown_label_fn(sdf.iloc[0]),
            method="update",
            args=[{"visible": visible}],
        ))

    fig.update_layout(
        title_text=None,
        margin=dict(t=150),
        updatemenus=[dict(
            buttons=dropdown_buttons, direction="down",
            x=0, xanchor="left", y=1.08, yanchor="top",
            showactive=True,
        )],
        annotations=list(fig.layout.annotations) + [select_caption],
        height=650,
    )
    return fig
