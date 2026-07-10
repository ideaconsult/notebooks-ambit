# + tags=["parameters"]
upstream = None
solr_url = None
solr_user_env = "ENM_USER"
solr_pass_env = "ENM_PWD"
product = None
# -

# Genotoxicity data-readiness dashboard for the eNanoMapper `metaenm` collection.
#
# This is NOT an inventory count — it answers the questions raised for the 2026 genotox paper
# (Genotox paper 2026.md): for the in-vitro COMET and Micronucleus studies, *how many are
# interpretable under the NanoREG2 / EFSA criteria*, and *what is missing*?
#
# NR2/EFSA interpretability needs, per study:
#   - at least 3 test concentrations            -> concentration_count_i >= 3
#   - a concurrent negative control             -> has_negative_control_b
#   - a positive control                        -> has_positive_control_b
#   - paired cytotoxicity / cell-viability data -> same nanomaterial has a Cell Viability study
#   - (COMET only) the +/-FPG variant           -> E.method_s == "COMET FPG"
#
# Data facts established by probing metaenm (drive the field choices below):
#   - in-vitro genotox  = endpointcategory_s:TO_GENETIC_IN_VITRO_SECTION (2428 studies)
#   - in-vivo  genotox  = endpointcategory_s:TO_GENETIC_IN_VIVO_SECTION  (599)
#   - cell viability    = endpointcategory_s:ENM_0000068_SECTION         (3349)  [ENM_0000068 = Cell Viability]
#   - COMET / COMET FPG / MICRONUCLEUS ASSAY are values of E.method_s (FPG is method-level, not a param)
#   - investigation_uuid_s is now populated in metaenm -> primary viability match is by
#     shared investigation_uuid_s (same protocol application group).
#   - not every genotox investigation has a matching viability investigation (only ~59/593
#     do), so studies with no investigation match fall back to EXPERIMENTAL CONTEXT: a
#     cytotoxicity study still counts as paired if it is the same lab + same nanomaterial +
#     same cell type. Fallback linkage key = (owner_name_s, s_uuid_s, cell_type).
#   - owner_name_s carries the source project (NanoGenotox, NANoREG, NanoReg2, PATROLS, ... — keep all)
#   - has_positive_control_b / has_negative_control_b only look at the _CONDITION_material_s
#     axis (classify_control() in study_metadata.py) -> a study can score False there yet
#     still identify its control via a PARAMETER: param_E.POSITIVE_CONTROLID_t,
#     param_E.POSITIVE_CONTROL_t, param_E.NEGATIVE_CONTROLID_t, param_E.NEGATIVE_CONTROL_t
#     (confirmed present in metaenm param_names_ss). Treat either signal as satisfying the
#     criterion — the condition-based flag is a false negative when only the param is set.

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth(os.environ[solr_user_env], os.environ[solr_pass_env])

GENOTOX_INVITRO = "TO_GENETIC_IN_VITRO_SECTION"
VIABILITY = "ENM_0000068_SECTION"  # Cell Viability

# In-study cytotoxicity / proliferation endpoints. For the micronucleus and comet assays the
# concurrent cytotoxicity control (OECD TG 487 / TG 489) is reported as an effect endpoint OF
# THE GENOTOX STUDY ITSELF — CBPI (Cytokinesis-Block Proliferation Index) for CBMN, the
# Replication / Relative-Proliferation indices (RI / RPD / RICC), plating efficiency, or an
# explicit viability endpoint for comet/MN — not as a separate study in the Cell Viability
# category. has_paired_viability() below therefore also accepts such an in-study endpoint as
# satisfying c_viab: the cytotoxicity data IS present, just carried on the genotox record.
# Confirmed against the live index across ALL projects (NanoGenotox 327, NAKNOWBASE, HARMLESS,
# NANOINFORMATIX, NanoTest, NANoREG, PLASTICHEAL, RISKGONE) — NOT nanotest-specific.
#
# Two match modes, because effectendpoint_ss is a composite "ENDPOINT (unit)" string:
#  * SUBSTRING markers — long, unambiguous phrases (safe as substrings).
#  * WHOLE-WORD markers — short acronyms (RI/RICC/RPD) matched on \b word boundaries so `RI`
#    does NOT match inside unrelated words, and so `GENOTOXICITY` (the genotox readout, which
#    must NEVER count as cytotoxicity) is never matched.
# TODO (source cleanup, see TODO_genotox_curation.md item 1e): rename these short-acronym
# endpoints to their long forms in the import configs so the WORD-marker workaround can be
# dropped — RI->REPLICATION_INDEX (NANOINFORMATIX/RISKGONE cbmn forms), RICC->
# RELATIVE_INCREASE_IN_CELL_COUNT (RISKGONE micronucleus), and fix the %_CELL_VIABILTIY typo
# (PLASTICHEAL micronucleus).
INSTUDY_CYTOTOX_SUBSTRING_MARKERS = (
    "CBPI",                          # Cytokinesis-Block(ed) Proliferation Index (CBMN cytotox)
    "PROLIFERATION_INDEX",           # covers CYTOKINESIS-BLOCK(ED)_PROLIFERATION_INDEX variants
    "CELL_COUNT_FOR_CBPI",           # CBPI input counts
    "REPLICATION_INDEX",             # comet/MN proliferation-based cytotoxicity (full form)
    "RELATIVE_POPULATION_DOUBLING",  # RPD (full form)
    "RELATIVE_INCREASE_IN_CELL_COUNT",  # RICC (full form)
    "CELL_VIABILITY",                # explicit viability endpoint on the study
    "CELL_VIABILTIY",                # observed misspelling in the live index (%_CELL_VIABILTIY)
    "PERCENTAGE_VIABILITY",          # PERCENTAGE_VIABILITY_COMPARED_TO_CONTROL (NANoREG)
    "VIABILITY_COMPARED_TO_CONTROL",
    "PLATING_EFFICIENCY",            # comet cytotoxicity (NANOINFORMATIX hprt)
    "CYTOTOXICITY",
)
INSTUDY_CYTOTOX_WORD_MARKERS = (
    "RI",     # Replication Index (short form, e.g. "RI (%)")
    "RICC",   # Relative Increase in Cell Count (acronym form)
    "RPD",    # Relative Population Doubling (acronym form)
)
import re as _re  # noqa: E402  (local helper; module already imports os/pandas above)
_INSTUDY_WORD_RE = _re.compile(
    r"\b(" + "|".join(_re.escape(m) for m in INSTUDY_CYTOTOX_WORD_MARKERS) + r")\b"
)


def has_instudy_cytotoxicity(effect_endpoints):
    """True if the genotox study carries its own cytotoxicity / proliferation endpoint
    (CBPI, RI, RPD, RICC, plating efficiency, viability, ...) — the concurrent cytotoxicity
    control required by OECD TG 487/489, reported on the genotox record itself rather than as a
    separate Cell Viability study. `GENOTOXICITY` is deliberately NOT matched."""
    if isinstance(effect_endpoints, (list, tuple, set)):
        ep = " ".join(map(str, effect_endpoints)).upper()
    else:
        ep = str(effect_endpoints).upper()
    if any(marker in ep for marker in INSTUDY_CYTOTOX_SUBSTRING_MARKERS):
        return True
    return bool(_INSTUDY_WORD_RE.search(ep))

# How a study's E.method_s value maps to an assay family for the matrix.
def assay_family(method_synonyms, method_name, effect_endpoints):
    # Convert endpoints to a single uppercase string
    if isinstance(effect_endpoints, (list, tuple, set)):
        ep = " ".join(map(str, effect_endpoints)).upper()
    else:
        ep = str(effect_endpoints).upper()

    # Use ontology IDs first
    if isinstance(method_synonyms, (list, tuple, set)) and method_synonyms:
        ids = set(map(str, method_synonyms))

        if "ENM_8000273" in ids:
            return "Micronucleus"

        if "OBI_0302736" in ids:
            # FPG-modified comet?
            if "FPG" in ep:
                return "COMET+FPG"
            return "COMET"

    # Fallback to method name
    m = str(method_name).upper()

    if "COMET" in m:
        if "FPG" in m or "FPG" in ep:
            return "COMET+FPG"
        return "COMET"

    if (
        "MICRONUCLEUS" in m
        or "CBMN" in m
        or m == "MN"
        or "CYTOKINESIS" in m
        or "OECD TG487" in m
    ):
        return "Micronucleus"

    return None


def fetch_docs(q, fl, rows=100000):
    """Page-free fetch (rows large enough for the genotox subset)."""
    r = requests.get(
        solr_url + "/select",
        params={"q": q, "rows": rows, "wt": "json", "fl": fl},
        auth=auth, timeout=300,
    ).json()
    return pd.DataFrame(r.get("response", {}).get("docs", []))


def context_keys(df):
    """Set of (owner, nanomaterial, cell_type) tuples for a study frame.

    cell_type (E.cell_type_ss) is multivalued, so explode it: a study contributes one key
    per cell type it used. Missing parts become '?' so a viability study with no recorded
    cell type still matches a genotox study with no recorded cell type for the same NM+lab.
    """
    d = df[["owner_name_s", "s_uuid_s", "E.cell_type_ss"]].copy()
    if "E.cell_type_ss" in d:
        d = d.explode("E.cell_type_ss")
    return set(map(tuple, d.fillna("?").astype(str).values))


# --- load the in-vitro genotox studies --------------------------------------------------
# param_* fields carry the parameter-based control evidence (positive/negative control
# identity or concentration), independent of the condition-based has_*_control_b flags.
PARAM_POS_FIELDS = ["param_E.POSITIVE_CONTROLID_t", "param_E.POSITIVE_CONTROL_t",
                    "param_E.POSITIVE_CONTROL_CONCENTRATION_t"]
PARAM_NEG_FIELDS = ["param_E.NEGATIVE_CONTROLID_t", "param_E.NEGATIVE_CONTROL_t",
                    "param_E.NEGATIVE_CONTROL_CONCENTRATION_t"]

# owner_name_s = the dataset/project (e.g. NANoREG); reference_owner_s = the actual study
# owner/lab from the citation record — distinct fields, both needed for curation.
# param___input_file_t = the original source file the study was imported from (param_ prefix
# + original "__input_file" name + _t suffix) — lets a curator find WHICH file/project needs
# attention, not just which study.
FL = ("document_uuid_s,s_uuid_s,publicname_s,owner_name_s,reference_owner_s,endpointcategory_s,"
      "E.method_s,E.method_synonym_ss,effectendpoint_ss, E.cell_type_ss,concentration_count_i,"
      "has_positive_control_b,has_negative_control_b,studyResultType_s,investigation_uuid_s,"
      "reference_s,reference_year_s,"
      "param___input_file_t,"
      + ",".join(PARAM_POS_FIELDS + PARAM_NEG_FIELDS))

gen = fetch_docs("type_s:metadata_study AND endpointcategory_s:{}".format(GENOTOX_INVITRO), FL)
print("in-vitro genotox studies:", len(gen))

# cell-viability studies: primary match key (investigation_uuid_s) + fallback context key
viab = fetch_docs("type_s:metadata_study AND endpointcategory_s:{}".format(VIABILITY), FL)
viability_investigations = set(viab["investigation_uuid_s"].dropna().astype(str))
viability_contexts = context_keys(viab)
print("viability investigations:", len(viability_investigations),
      " | viability (owner,NM,cell) contexts:", len(viability_contexts))

# --- derive per-study readiness flags ---------------------------------------------------

gen["assay"] = gen.apply(
    lambda row: assay_family(
        row["E.method_synonym_ss"],
        row["E.method_s"],
        row["effectendpoint_ss"],
    ),
    axis=1,
)
gen = gen[gen["assay"].notna()].copy()        # COMET / COMET+FPG / Micronucleus only
print("COMET/MN studies:", len(gen))

for col in ("has_positive_control_b", "has_negative_control_b"):
    if col not in gen:
        gen[col] = False
    gen[col] = gen[col].fillna(False).astype(bool)
gen["concentration_count_i"] = gen.get("concentration_count_i", 0)
gen["concentration_count_i"] = pd.to_numeric(gen["concentration_count_i"], errors="coerce").fillna(0).astype(int)

gen["c_conc3"] = gen["concentration_count_i"] >= 3

# a param field is "evidence" if the column exists and the row has a non-null value
def has_any_param(df, fields):
    present = [f for f in fields if f in df.columns]
    if not present:
        return pd.Series(False, index=df.index)
    return df[present].notna().any(axis=1)

gen["c_pos_via_param"] = has_any_param(gen, PARAM_POS_FIELDS)
gen["c_neg_via_param"] = has_any_param(gen, PARAM_NEG_FIELDS)

# condition-based flag OR parameter-based evidence — either satisfies the criterion
gen["c_neg"] = gen["has_negative_control_b"] | gen["c_neg_via_param"]
gen["c_pos"] = gen["has_positive_control_b"] | gen["c_pos_via_param"]

# Investigations that contain at least one study carrying an in-study cytotoxicity/
# proliferation endpoint (CBPI, RICC, ...). For CBMN the micronucleus-COUNT study (BMN
# template) and the CBPI proliferation-index study are SEPARATE protocol applications of the
# SAME experiment, sharing one INVESTIGATION_UUID; a protocol application cannot hold two
# endpoint categories, so the CBPI cytotoxicity cannot live on the MN study directly. Instead,
# a genotox study counts as having paired cytotoxicity if ANY study in its investigation (its
# CBPI sibling, or itself) carries a cytotox endpoint. This is the shared-experiment linkage
# the domain expert described (same partner+method+cell, across materials/readouts).
_gen_has_instudy_cytotox = gen["effectendpoint_ss"].apply(has_instudy_cytotoxicity)
investigations_with_cytotox = set(
    gen.loc[_gen_has_instudy_cytotox, "investigation_uuid_s"].dropna().astype(str)
)

# paired viability: primary match is a shared investigation_uuid_s (same protocol
# application group). Falls back to experimental-context matching — (owner, NM, cell type) —
# when the study has no investigation_uuid_s, or its investigation has no viability match.
# Third path: the study carries its OWN cytotoxicity/proliferation endpoint (CBPI, RI, ...).
# Fourth path: a SIBLING study in the same investigation carries one (MN <- its CBPI sibling).
def has_paired_viability(row):
    inv = row.get("investigation_uuid_s")
    if pd.notna(inv) and str(inv) in viability_investigations:
        return True

    if has_instudy_cytotoxicity(row.get("effectendpoint_ss")):
        return True

    if pd.notna(inv) and str(inv) in investigations_with_cytotox:
        return True

    cells = row["E.cell_type_ss"]
    cells = cells if isinstance(cells, list) else ([cells] if pd.notna(cells) else ["?"])
    owner = str(row["owner_name_s"]) if pd.notna(row["owner_name_s"]) else "?"
    nm = str(row["s_uuid_s"]) if pd.notna(row["s_uuid_s"]) else "?"
    return any((owner, nm, str(c)) in viability_contexts for c in cells)

gen["c_viab"] = gen.apply(has_paired_viability, axis=1)
gen["c_viab_via_investigation"] = (
    gen["investigation_uuid_s"].astype(str).isin(viability_investigations)
    & gen["investigation_uuid_s"].notna()
)
gen["c_viab_via_instudy"] = _gen_has_instudy_cytotox
gen["c_viab_via_sibling_cytotox"] = (
    gen["investigation_uuid_s"].astype(str).isin(investigations_with_cytotox)
    & gen["investigation_uuid_s"].notna()
    & ~_gen_has_instudy_cytotox   # sibling carries it, not this study itself
)
gen["interpretable"] = gen["c_conc3"] & gen["c_neg"] & gen["c_pos"] & gen["c_viab"]
gen["owner_name_s"] = gen.get("owner_name_s", "unknown").fillna("unknown")

# ========================================================================================
# 1. READINESS FUNNEL — cumulative survival through the NR2 criteria
# ========================================================================================
steps = [
    ("All COMET/MN studies", len(gen)),
    ("≥ 3 concentrations", int(gen["c_conc3"].sum())),
    ("+ negative control", int((gen["c_conc3"] & gen["c_neg"]).sum())),
    ("+ positive control", int((gen["c_conc3"] & gen["c_neg"] & gen["c_pos"]).sum())),
    ("+ paired viability", int(gen["interpretable"].sum())),
]
funnel = pd.DataFrame(steps, columns=["criterion", "studies"])
fig = go.Figure(go.Funnel(
    y=funnel["criterion"], x=funnel["studies"],
    textinfo="value+percent initial",
))
fig.update_layout(title="NR2 interpretability funnel — in-vitro COMET / Micronucleus")
fig.show()

# ========================================================================================
# 2. PER-CRITERION COVERAGE BY SOURCE (owner_name_s) — keep every project
# ========================================================================================
crit_cols = {"c_conc3": "≥3 conc", "c_neg": "neg ctrl",
             "c_pos": "pos ctrl", "c_viab": "viability", "interpretable": "interpretable"}
by_owner = (
    gen.groupby("owner_name_s")
    .agg(total=("document_uuid_s", "size"),
         **{lbl: (col, "sum") for col, lbl in crit_cols.items()})
    .reset_index()
    .sort_values("total", ascending=False)
)
# coverage as % of that source's studies
cov = by_owner.copy()
for lbl in crit_cols.values():
    cov[lbl] = (cov[lbl] / cov["total"] * 100).round(0)
cov_long = cov.melt(id_vars=["owner_name_s", "total"],
                    value_vars=list(crit_cols.values()),
                    var_name="criterion", value_name="pct")
fig = px.bar(
    cov_long, x="owner_name_s", y="pct", color="criterion", barmode="group",
    title="Criterion coverage (% of studies) by source project",
    labels={"pct": "% of source's studies", "owner_name_s": "source (owner_name_s)"},
)
fig.update_layout(xaxis_tickangle=-45)
fig.show()

print("Per-source readiness (absolute counts):")
print(by_owner.to_string(index=False))

# ========================================================================================
# 3. NANOMATERIAL × ASSAY READINESS MATRIX
#    For each NM (publicname_s), best readiness state per assay family.
#    2=interpretable, 1=present-but-incomplete, 0=absent
# ========================================================================================
gen["nm"] = gen["publicname_s"].fillna(gen["s_uuid_s"]).fillna("?")
state = (
    gen.assign(state=gen["interpretable"].map({True: 2, False: 1}))
    .groupby(["nm", "assay"])["state"].max()
    .unstack(fill_value=0)
)
# show the NMs with the most coverage first, cap to keep the heatmap readable
state["_score"] = state.sum(axis=1)
state = state.sort_values("_score", ascending=False).drop(columns="_score").head(40)
fig = px.imshow(
    state, aspect="auto", color_continuous_scale=[(0, "#eee"), (0.5, "#fbb"), (1, "#2a8")],
    title="Nanomaterial × assay readiness (2=interpretable, 1=incomplete, 0=absent) — top 40 NMs",
    labels={"x": "assay", "y": "nanomaterial", "color": "readiness"},
)
fig.update_layout(height=900)
fig.show()

# ========================================================================================
# 4. THE GAP — for studies that fail, which criterion is missing most?
# ========================================================================================
fails = gen[~gen["interpretable"]]
gap = pd.DataFrame({
    "missing": ["< 3 concentrations", "no negative control",
                "no positive control", "no paired viability"],
    "studies": [int((~fails["c_conc3"]).sum()), int((~fails["c_neg"]).sum()),
                int((~fails["c_pos"]).sum()), int((~fails["c_viab"]).sum())],
}).sort_values("studies")
fig = px.bar(gap, x="studies", y="missing", orientation="h",
             title="Why studies are not interpretable — missing criterion (counts overlap)")
fig.show()

# ========================================================================================
# 5. ASSAY BREAKDOWN incl. COMET ±FPG (a specific paper question)
# ========================================================================================
assay_counts = gen["assay"].value_counts().reset_index()
assay_counts.columns = ["assay", "studies"]
fig = px.bar(assay_counts, x="assay", y="studies",
             title="Study count by assay family (COMET vs COMET+FPG vs Micronucleus)")
fig.show()

# summary line for the notebook log
print("\nSUMMARY")
print("  COMET/MN in-vitro studies:", len(gen))
print("  fully interpretable (all 4 NR2 criteria):", int(gen["interpretable"].sum()))
print("  distinct nanomaterials covered:", gen["nm"].nunique())
print("  NMs with at least one interpretable study:",
      gen[gen["interpretable"]]["nm"].nunique())
print("  paired-viability matches via investigation_uuid_s:",
      int(gen["c_viab_via_investigation"].sum()))
print("  paired-viability satisfied by in-study cytotoxicity endpoint (CBPI/RI/...):",
      int(gen["c_viab_via_instudy"].sum()))
print("  paired-viability satisfied by a sibling study's cytotoxicity (shared investigation):",
      int(gen["c_viab_via_sibling_cytotox"].sum()))
print("  paired-viability satisfied ONLY by in-study cytotoxicity endpoint:",
      int((gen["c_viab_via_instudy"] & ~gen["c_viab_via_investigation"]).sum()))
print("  paired-viability matches via context fallback (excl. investigation & in-study):",
      int((gen["c_viab"] & ~gen["c_viab_via_investigation"] & ~gen["c_viab_via_instudy"]).sum()))
print("  positive control rescued by param evidence only (condition flag was False):",
      int((gen["c_pos_via_param"] & ~gen["has_positive_control_b"]).sum()))
print("  negative control rescued by param evidence only (condition flag was False):",
      int((gen["c_neg_via_param"] & ~gen["has_negative_control_b"]).sum()))

# ========================================================================================
# 6. TASK OUTPUT — full per-study table with all readiness flags, for downstream use
#    (the paper authors, or a future Solr re-import of the readiness annotation)
# ========================================================================================
gen.to_csv(product["data"], index=False)
print("\nwrote", len(gen), "rows to", product["data"])
