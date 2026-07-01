# + tags=["parameters"]
upstream = ["viz_metadata"]
filter_tag = ""                # matches the s_uuid_s server tag (e.g. "NNRG" = NanoREG, public)
filter_project = ""            # matches owner_name_s
filter_s_uuid = ""             # matches s_uuid_s
filter_document_uuid = ""      # matches document_uuid_s
filter_investigation_uuid = ""  # matches investigation_uuid_s
max_studies = 50               # safety cap on how many failing studies to fetch/plot
product = None
# -

# Genotox curation — retrieve & plot the ACTUAL data for FAILING studies.
#
# viz_metadata.py flags which in-vitro COMET/Micronucleus studies FAIL the NR2/EFSA
# interpretability criteria (>=3 concentrations, neg control, pos control, paired viability)
# and exports one row per study (document_uuid_s) to a CSV. That CSV only carries summary
# metadata. To curate a failing study a human needs the REAL dose-response data — to tell a
# true data gap from a metadata/indexing artefact (e.g. concentration_count_i == 0 because the
# dose axis was not captured as a Solr condition, even though the study has a real dose series).
#
# This task: read the readiness CSV -> pick failing studies (ANY criterion failed) -> group by
# substance -> fetch each substance's in-vitro genotox studies ONCE from its source AMBIT server
# -> keep only the failing document_uuids -> plot the dose-response as an interactive Plotly
# dashboard (HTML).
#
# Verified against live data:
#   - document_uuid_s == the AMBIT study "uuid"
#   - {server}/substance/{s_uuid}/study?media=application/json&top=TOX
#         &category=TO_GENETIC_IN_VITRO_SECTION  returns only the in-vitro genotox studies
#   - effects2df(papp.effects) yields CONCENTRATION (dose), material (treatment/control) and
#     loValue/unit (result) columns — directly plottable
#   - some servers are PROTECTED (NGTX/NanoGenotox, RGNE/RISKGONE return 403) -> skip + record.
#     nanoreg1 (NNRG) and data.enanomapper.net (ENM) are public.

import sys

# Use the clean pyambit-main checkout (the editable `pyambit` install has an unresolved merge
# conflict in datamodel.py).
sys.path.insert(0, "d:/nina/src/charisma/pyambit-main/src")

import pandas as pd
import plotly.graph_objects as go
import requests
from plotly.subplots import make_subplots

from pyambit.datamodel import Study, effects2df

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


# --- select failing studies -----------------------------------------------------------------
csv_path = upstream["viz_metadata"]["data"]
df = pd.read_csv(csv_path)
print("readiness rows:", len(df))

sel = df[~df["interpretable"].astype(bool)].copy()     # a study fails if ANY criterion failed
print("failing studies:", len(sel))

# optional filters, OR-combined
masks = []
if filter_tag:
    masks.append(sel["s_uuid_s"].str.split("-").str[0] == filter_tag)
if filter_project:
    masks.append(sel["owner_name_s"] == filter_project)
if filter_s_uuid:
    masks.append(sel["s_uuid_s"] == filter_s_uuid)
if filter_document_uuid:
    masks.append(sel["document_uuid_s"] == filter_document_uuid)
if filter_investigation_uuid and "investigation_uuid_s" in sel.columns:
    masks.append(sel["investigation_uuid_s"] == filter_investigation_uuid)
if masks:
    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m
    sel = sel[combined]
    print("after OR filters:", len(sel))

sel = sel.head(max_studies)

# group failing document_uuids by substance -> fetch each substance once
failing_by_substance = sel.groupby("s_uuid_s")["document_uuid_s"].apply(set).to_dict()
# map document_uuid -> a readable label for the plot
label_by_doc = {
    row["document_uuid_s"]: "{} | {} | {}".format(
        row.get("owner_name_s", ""), row.get("publicname_s", ""), row["document_uuid_s"][:13]
    )
    for _, row in sel.iterrows()
}
print("substances to fetch:", len(failing_by_substance))

# --- fetch + collect dose-response frames ---------------------------------------------------
panels = []          # (label, dataframe) per matched failing study
not_retrieved = []   # rows for the "could not retrieve" curation finding

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
            continue                      # only the specific failing document_uuids
        if not papp.effects:
            continue
        eff = effects2df(papp.effects)
        edf = eff[0]
        if edf is None or edf.empty:
            continue
        panels.append((label_by_doc.get(papp.uuid, papp.uuid), edf))
    # any wanted doc that the server didn't return
    for doc in wanted - fetched_uuids:
        not_retrieved.append({"document_uuid_s": doc, "s_uuid_s": s_uuid,
                              "owner_name_s": owner, "reason": "study not returned by server"})

print("plottable panels:", len(panels))
print("not retrieved:", len(not_retrieved))


# --- pick x (dose) and y (result) columns from an effects2df frame --------------------------
def dose_axis(edf):
    for c in ("CONCENTRATION", "CONCENTRATION_MASS", "DOSE", "concentration", "dose"):
        if c in edf.columns:
            return c
    return None


# --- build the interactive dashboard --------------------------------------------------------
if panels:
    n = len(panels)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    fig = make_subplots(rows=rows, cols=cols,
                        subplot_titles=[lbl for lbl, _ in panels])
    for i, (lbl, edf) in enumerate(panels):
        rr = i // cols + 1
        cc = i % cols + 1
        x = dose_axis(edf)
        y = "loValue" if "loValue" in edf.columns else None
        color_col = "material" if "material" in edf.columns else None
        if x is None or y is None:
            # nothing dose-shaped: fall back to a bar of endpoint vs loValue
            if "endpoint" in edf.columns and "loValue" in edf.columns:
                fig.add_trace(go.Bar(x=edf["endpoint"], y=edf["loValue"], name=lbl),
                              row=rr, col=cc)
            continue
        if color_col:
            for treat, g in edf.groupby(color_col):
                fig.add_trace(
                    go.Scatter(x=g[x], y=g[y], mode="markers+lines",
                               name=str(treat), legendgroup=str(treat),
                               showlegend=(i == 0)),
                    row=rr, col=cc,
                )
        else:
            fig.add_trace(go.Scatter(x=edf[x], y=edf[y], mode="markers+lines", name=lbl),
                          row=rr, col=cc)
        fig.update_xaxes(title_text=x, row=rr, col=cc)
        fig.update_yaxes(title_text=y, row=rr, col=cc)

    fig.update_layout(
        height=350 * rows,
        title_text="Dose-response for FAILING genotox studies (curation view)",
    )
    fig.write_html(product["data"])
    fig.show()
else:
    # still write a valid (empty) html so the product exists
    go.Figure().update_layout(
        title_text="No plottable failing studies for the current filter"
    ).write_html(product["data"])
    print("no panels to plot")

# --- curation finding: studies that could not be retrieved ----------------------------------
if not_retrieved:
    nr = pd.DataFrame(not_retrieved)
    print("\nCOULD NOT RETRIEVE (protected server / missing):")
    print(nr.groupby("reason").size().to_string())
    print(nr.to_string(index=False))
