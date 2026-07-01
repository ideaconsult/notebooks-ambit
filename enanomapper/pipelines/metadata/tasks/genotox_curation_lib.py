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

import numpy as np
import pandas as pd
import requests

from pyambit.datamodel import Study
from pyambit import study_config as sc

GENOTOX_INVITRO = "TO_GENETIC_IN_VITRO_SECTION"

# --- AMBIT server resolution (ported from spectrasearch-viewers/src/utils/tagdbs.js) ---------
# 4-letter tag = prefix before the first "-" in s_uuid_s -> AMBIT server base URL.
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


def substance2server(s_uuid):
    """4-letter tag (prefix before first '-') -> AMBIT server base URL, or None if unknown."""
    if not s_uuid:
        return None
    tag = s_uuid.split("-")[0] if "-" in s_uuid else s_uuid
    return TAG_DBS.get(tag)


def fetch_genotox_studies(server, s_uuid):
    """Fetch a substance's in-vitro genotox studies from AMBIT.

    Returns (list_of_ProtocolApplication, reason) — reason is None on success, else a short
    string ('unknown server tag', 'HTTP 403', 'not JSON', 'error: ...') for the skip list.
    """
    url = "{}/substance/{}/study".format(server.rstrip("/"), s_uuid)
    try:
        r = requests.get(
            url,
            params={"media": "application/json", "top": "TOX",
                    "category": GENOTOX_INVITRO},
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


def fetch_and_flatten(sel, failing_by_substance, label_by_doc, extra_meta_fn):
    """Fetch AMBIT data for every (substance, wanted document_uuids) pair and flatten to a
    long dose-response DataFrame.

    sel: the filtered readiness rows (DataFrame), one row per document_uuid_s.
    failing_by_substance: {s_uuid_s: set(document_uuid_s)} — despite the name (kept for
        continuity with curate_failing.py), this is just "selected studies grouped by
        substance" — used for both the failing and passing tasks.
    label_by_doc: {document_uuid_s: label string} for the plot/table.
    extra_meta_fn(row) -> dict: per-study extra metadata merged into `meta` (e.g. "fails" for
        curate_failing, "assay"/"studyResultType_s" for curate_passing).

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

        studies, reason = fetch_genotox_studies(server, s_uuid)
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
                "substance_url": "{}/substance/{}".format(server.rstrip("/"), s_uuid),
                "study_url": "{}/substance/{}/study?media=application/json&category={}"
                             .format(server.rstrip("/"), s_uuid, GENOTOX_INVITRO),
                **extra_meta_fn(row),
            }
            study_rows = study_to_long_rows(papp, meta)
            if study_rows:
                study_doses = [r["dose"] for r in study_rows if r["dose"] is not None]
                study_min_dose = min(study_doses) if study_doses else 1.0
                long_rows.extend(study_rows)
                long_rows.extend({**meta, **r} for r in param_control_rows(papp, study_min_dose))
            else:
                not_retrieved.append({"document_uuid_s": papp.uuid, "s_uuid_s": s_uuid,
                                      "owner_name_s": owner,
                                      "reason": "retrieved but no dose-response array"})
        for doc in wanted - fetched_uuids:
            not_retrieved.append({"document_uuid_s": doc, "s_uuid_s": s_uuid,
                                  "owner_name_s": owner, "reason": "study not returned by server"})

    return pd.DataFrame(long_rows), not_retrieved


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
