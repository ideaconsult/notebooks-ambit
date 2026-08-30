# + tags=["parameters"]
upstream = ["viz_metadata"]
product = None
# -

# How would studies group into one property, using only the identity curate_passing.py /
# curate_failing.py already treat as defining -- material, endpoint category, assay method,
# cell type? Nothing from parameters beyond that: no operator, no preparation date, no input
# filename, no free-text notes. Contrast this against pyambit.bmd.PropertyKey, which folds
# EVERY leftover ProtocolApplication parameter into the key verbatim (`other_parameters` in
# series_from_protocol_application) -- so two labs' operator names or prep dates differing
# is enough to split what should be one consolidatable property into two, which is why
# every property in the last bmd_embedding run came out with n_providers == 1 even for
# materials with clearly multi-laboratory data.
#
# Source is viz_metadata's own readiness table -- no re-fetch from AMBIT, so this is a
# grouping-logic review, not a new data pull. Exposure time is not in that table (viz_metadata
# does not carry it), so it is reported per study where available only as a caveat column;
# the group key here is (material, category, method, cell type), matching what curate_*
# actually uses to label and pair studies (E.method_s, E.cell_type_ss, publicname_s).

import pandas as pd

df = pd.read_csv(upstream["viz_metadata"]["data"])
print("studies:", len(df))

GROUP_COLS = ["publicname_s", "endpointcategory_s", "E.method_s", "E.cell_type_ss"]
GROUP_COLS = [c for c in GROUP_COLS if c in df.columns]
print("grouping on:", GROUP_COLS)

studies = df.copy()
studies["group_key"] = studies[GROUP_COLS].astype(str).agg(" | ".join, axis=1)

groups = (
    studies.groupby("group_key", dropna=False)
    .agg(
        n_studies=("document_uuid_s", "nunique"),
        n_labs=("reference_owner_s", "nunique"),
        n_projects=("owner_name_s", "nunique"),
        n_substances=("s_uuid_s", "nunique"),
        labs=("reference_owner_s", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        projects=("owner_name_s", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        substances=("s_uuid_s", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
    )
    .reset_index()
)
for col in GROUP_COLS:
    groups[col] = groups["group_key"].map(
        dict(zip(studies["group_key"], studies[col]))
    )
groups = groups[GROUP_COLS + ["n_studies", "n_labs", "n_projects", "n_substances",
                              "labs", "projects", "substances", "group_key"]]
groups = groups.sort_values(["n_labs", "n_studies"], ascending=False)

print("\ngroups:", len(groups))
n_multi_lab = int((groups["n_labs"] >= 2).sum())
print("groups with >=2 distinct laboratories: {} / {} ({:.1f}%)".format(
    n_multi_lab, len(groups), 100 * n_multi_lab / len(groups)))
n_multi_project = int((groups["n_projects"] >= 2).sum())
print("groups spanning >=2 distinct projects (owner_name_s): {} / {} ({:.1f}%)".format(
    n_multi_project, len(groups), 100 * n_multi_project / len(groups)))
n_multi_substance = int((groups["n_substances"] >= 2).sum())
print("groups spanning >=2 distinct AMBIT substance records (s_uuid_s): {} / {} ({:.1f}%)".format(
    n_multi_substance, len(groups), 100 * n_multi_substance / len(groups)))

print("\ntop 10 groups by number of laboratories:")
print(groups.head(10)[GROUP_COLS + ["n_studies", "n_labs", "n_substances"]].to_string(index=False))

study_detail_cols = [
    c for c in (
        "document_uuid_s", "s_uuid_s", "owner_name_s", "reference_owner_s",
        "publicname_s", "endpointcategory_s", "E.method_s", "E.cell_type_ss",
        "reference_s", "reference_year_s", "group_key",
    )
    if c in studies.columns
]

with pd.ExcelWriter(product["data"], engine="openpyxl") as writer:
    groups.to_excel(writer, sheet_name="groups", index=False)
    studies[study_detail_cols].sort_values("group_key").to_excel(
        writer, sheet_name="studies", index=False
    )
print("\nwrote", product["data"])
print("  sheet 'groups':  one row per (material, category, method, cell type) group")
print("  sheet 'studies': one row per study, with its group key, sorted so a group's")
print("                   studies sit together")
