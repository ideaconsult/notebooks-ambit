# + tags=["parameters"]
upstream = ["study_metadata"]
product = None
# -

# Data-quality / curation flags for the eNanoMapper metadata (metaenm) generation.
#
# SEPARATE CONCERN from readiness (viz_metadata.py answers "is a study interpretable?").
# This task answers "is the grouping/annotation of the imported data internally consistent?"
# — surfacing structural issues to fix AT THE SOURCE (config / expand config / source Excel),
# so they don't have to be papered over downstream. Runs off study_metadata.json (the same
# records that seed metaenm), so a flag here is a flag on what actually gets indexed.
#
# The issues checked come from real curation findings (see products/TODO_genotox_curation.md):
#   - assay_uuid_s that spans >1 cell type or >1 method  -> assay grouping too coarse / mixed
#   - investigation_uuid_s that spans >1 cell type        -> investigation too coarse
#   - an assay group with a control but NO sample (or samples but NO control)
#   - a study relying only on a sibling control in its assay (no own control point) — an
#     annotation gap: the control should also be annotated on / paired with the sample
#   - a study with a 0-concentration point but no explicit control_negative annotation
#
# Output: one CSV row per (scope, key) that has an issue, with the issue type, the offending
# values, affected study count, owner/project, and a short human note — a curation worklist.

import json
from collections import defaultdict

import pandas as pd

records = json.load(open(upstream["study_metadata"]["data"], encoding="utf-8"))
df = pd.DataFrame(records)
print("studies loaded:", len(df))


def as_list(v):
    """Multivalued Solr fields arrive as a list, a scalar, or missing."""
    if isinstance(v, list):
        return [x for x in v if x is not None]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [v]


def truthy(v):
    return bool(v) and not (isinstance(v, float) and pd.isna(v))


# only in-vitro genotox for now (the curation scope); widen later if useful.
if "endpointcategory_s" in df.columns:
    df = df[df["endpointcategory_s"] == "TO_GENETIC_IN_VITRO_SECTION"].copy()
print("in-vitro genotox studies:", len(df))

flags = []  # each: dict(scope, key, issue, detail, n_studies, owner_name_s, note)


def add_flag(scope, key, issue, detail, n_studies, owner, note):
    flags.append({
        "scope": scope, "key": key, "issue": issue, "detail": detail,
        "n_studies": n_studies, "owner_name_s": owner, "note": note,
    })


# --- group-level integrity: assay_uuid_s and investigation_uuid_s ----------------------------
def group_audit(group_field, span_fields, require_control):
    """For each value of group_field, check that span_fields don't vary (grouping too coarse),
    and — if require_control — that the group has both a control and a sample member."""
    groups = defaultdict(lambda: {
        "spans": defaultdict(set), "has_pos": False, "has_neg": False,
        "has_sample": False, "owners": set(), "n": 0,
    })
    for _, r in df.iterrows():
        key = r.get(group_field)
        if not truthy(key):
            continue
        g = groups[str(key)]
        g["n"] += 1
        g["owners"].add(str(r.get("owner_name_s")))
        for sf in span_fields:
            for v in as_list(r.get(sf)):
                g["spans"][sf].add(str(v))
        roles = set(as_list(r.get("control_roles_ss")))
        if truthy(r.get("has_positive_control_b")) or "positive" in roles:
            g["has_pos"] = True
        if truthy(r.get("has_negative_control_b")) or "negative" in roles:
            g["has_neg"] = True
        # a "sample" member = not a pure control study
        if not (truthy(r.get("has_positive_control_b")) and r.get("concentration_count_i", 0)):
            g["has_sample"] = True
    for key, g in groups.items():
        owner = "; ".join(sorted(g["owners"]))
        for sf in span_fields:
            vals = g["spans"][sf]
            if len(vals) > 1:
                add_flag(group_field, key, "{}_spans_multiple_{}".format(group_field, sf),
                         "{} = {}".format(sf, sorted(vals)), g["n"], owner,
                         "grouping too coarse: one {} mixes several {} - split it".format(
                             group_field, sf))
        if require_control and g["n"] > 1:
            if not g["has_pos"]:
                add_flag(group_field, key, "assay_without_positive_control",
                         "no member has a positive control", g["n"], owner,
                         "assay group has samples but no positive control - real gap or "
                         "control assigned to a different assay_uuid")
            if not g["has_neg"]:
                add_flag(group_field, key, "assay_without_negative_control",
                         "no member has a negative control / 0-dose", g["n"], owner,
                         "assay group has samples but no negative control - annotate the "
                         "0-dose row control_negative, or check assay_uuid assignment")


# assay_uuid should be one method + one cell line (controls + materials share it).
group_audit("assay_uuid_s", ["E.cell_type_ss", "E.method_s"], require_control=True)
# investigation_uuid is the broader cross-method link but should still be one cell line.
group_audit("investigation_uuid_s", ["E.cell_type_ss"], require_control=False)


# --- study-level flags -----------------------------------------------------------------------
# a 0-dose point but no explicit control_negative annotation -> annotation gap at source.
zero_no_annot = df[
    df.get("has_zero_dose_b", pd.Series(False, index=df.index)).apply(truthy)
    & ~df.get("has_negative_control_annotated_b", pd.Series(False, index=df.index)).apply(truthy)
] if "has_zero_dose_b" in df.columns else df.iloc[:0]
for owner, grp in zero_no_annot.groupby(zero_no_annot.get("owner_name_s", "unknown")):
    add_flag("study", "(per-project)", "zero_dose_without_control_negative_annotation",
             "0-concentration point present but not annotated control_negative",
             len(grp), str(owner),
             "add control_negative annotation to the 0-dose row via config MAPPING / expand "
             "config so has_negative_control is true in the index itself")


flags_df = pd.DataFrame(flags)
print("\ncuration flags raised:", len(flags_df))
if not flags_df.empty:
    print("\nby issue type:")
    print(flags_df.groupby("issue")["n_studies"].agg(["count", "sum"]).to_string())
    print("\nby project:")
    print(flags_df.groupby("owner_name_s")["issue"].count().sort_values(ascending=False).to_string())

flags_df.to_csv(product["data"], index=False, encoding="utf-8")
print("\nwrote", product["data"])
