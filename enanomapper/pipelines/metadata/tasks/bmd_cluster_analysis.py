# + tags=["parameters"]
upstream = ["bmd_embedding", "bmd_clustering"]
product = None
# -

# Does the clustering mean anything?
#
# Kept as its own task, separate from bmd_clustering.py, so a new check here never
# requires re-running k-means or re-fetching from AMBIT: it reads bmd_embedding's vectors
# (for the raw 96-d vector, n_providers, n_determined) and bmd_clustering's small output
# (for the cluster id and the 2-d picture), joins them on id, and stops there.
#
# A BMD vector should describe the material's property, not which laboratory measured it,
# and not merely whether a benchmark response was reached at all. Checked in order:
# whether cross-laboratory consolidation happened at all (it has to, before any
# lab-vs-material comparison below means anything); whether the vectors are mode-collapsed
# onto the undetermined/censoring fill; what the dominant direction of variance tracks;
# whether a same-material pair is closer than a different-material pair within one method;
# and what is actually inside each cluster by name, not just by count.

import numpy as np
import pandas as pd
import plotly.express as px

vectors = pd.read_csv(upstream["bmd_embedding"]["data_csv"])
clusters = pd.read_csv(upstream["bmd_clustering"]["data"])
df = vectors.merge(clusters[["id", "cluster", "pc1", "pc2"]], on="id", how="inner")
print("properties:", len(df), "(", len(vectors) - len(df), "dropped by the join, if any)")
if df.empty:
    raise SystemExit("no properties to analyse - run bmd_embedding and bmd_clustering first")

vector_cols = sorted(c for c in df.columns if c.startswith("v") and c[1:].isdigit())
X = df[vector_cols].to_numpy(dtype=float)
k = int(df["cluster"].nunique())
print("clusters:", k)

# --- has any cross-laboratory consolidation actually happened? --------------------------
# consolidate_providers exists to mix >=2 laboratories into one BMD distribution. If every
# property has exactly one provider, that mixing never ran: n_providers==1 makes
# `consolidate_providers` degenerate to that one laboratory's own bootstrap, and (material,
# method, laboratory) become nearly a bijection -- at which point "the embedding tracks
# laboratory" and "the embedding tracks method" are the same statistical statement, not two
# competing explanations. Check this BEFORE trusting any variance-share number below.
print("\nn_providers distribution:")
print(df["n_providers"].value_counts().sort_index().to_string())
n_multi = int((df["n_providers"] >= 2).sum())
print("properties with >=2 providers: {} / {} ({:.1f}%)".format(
    n_multi, len(df), 100 * n_multi / len(df)))
if n_multi == 0:
    print("WARNING: no cross-laboratory consolidation occurred anywhere in this cohort.")
    print("  Every property is a single laboratory's own estimate. Any lab-vs-material")
    print("  variance-share comparison below is confounded and cannot be trusted: with one")
    print("  provider per property, laboratory, method and concentration unit are close to")
    print("  a bijection, so a high laboratory eta2 does not distinguish 'the embedding")
    print("  learned provenance' from 'the embedding learned method'.")
    print("  Likely cause: series_from_substance groups within ONE AMBIT substance record")
    print("  (one s_uuid) at a time. In a federated set of ~10 project databases the same")
    print("  physical reference material (e.g. an NM-series or JRC code) is commonly")
    print("  registered under a SEPARATE s_uuid per project, so two laboratories that both")
    print("  measured 'the same' material never land in one SubstanceRecord and never reach")
    print("  consolidate_providers together. Fix: consolidate across s_uuid values sharing")
    print("  a known reference-material identity, not only within one substance record.")

# --- is the vector itself informative, or mode-collapsed? -------------------------------
# A property whose bootstrap draws never bracket a benchmark response produces a vector
# pinned at BmdSpec.log_window's edge for every quantile at that level (bmd_vector's
# documented fill). If that happens for most properties, many vectors become near-identical
# regardless of material, and no clustering on them means anything.
row_range = np.ptp(X, axis=1)
n_constant = int((row_range < 1e-9).sum())
print("\nvectors with zero range (every entry equal -- fully undetermined or fully censored "
      "at the window edge): {} / {} ({:.1f}%)".format(
          n_constant, len(df), 100 * n_constant / len(df)))
rounded = np.round(X, 4)
n_distinct = len({tuple(row) for row in rounded})
print("distinct vectors (rounded to 1e-4 decades): {} / {} rows".format(n_distinct, len(df)))
if n_distinct < 0.5 * len(df):
    print("WARNING: fewer than half the vectors are distinct. Before reading anything into")
    print("  the clusters, check n_determined below -- widespread mode collapse means the")
    print("  vectors are dominated by the undetermined/censoring fill, not by biology.")
print("\nn_determined distribution (how many of the requested benchmark responses were")
print("actually reached, per property):")
print(df["n_determined"].value_counts().sort_index().to_string())

# --- variance share ------------------------------------------------------------------
def variance_share(values, groups):
    """Fraction of total variance explained by group membership (eta squared)."""
    values = np.asarray(values, dtype=float)
    groups = pd.Series(groups).fillna("?").astype(str).to_numpy()
    grand = values.mean()
    total = float(np.sum((values - grand) ** 2))
    if total <= 0:
        return 0.0
    between = 0.0
    for g in np.unique(groups):
        member = values[groups == g]
        between += member.size * (member.mean() - grand) ** 2
    return float(between / total)


print("\nvariance share of PC1 / PC2 by grouping (eta squared):")
print("{:<22}{:>8}{:>8}".format("grouping", "PC1", "PC2"))
diagnostics = []
for name, column in (
    ("laboratory", "providers"),
    ("material", "substance"),
    ("method", "method"),
    ("endpoint", "endpoint"),
    ("category", "endpointcategory_s"),
):
    if column not in df.columns:
        continue
    pc1 = variance_share(df["pc1"], df[column])
    pc2 = variance_share(df["pc2"], df[column])
    diagnostics.append({"grouping": name, "pc1_eta2": pc1, "pc2_eta2": pc2})
    print("{:<22}{:>8.3f}{:>8.3f}".format(name, pc1, pc2))

diag = pd.DataFrame(diagnostics)
if not diag.empty and {"laboratory", "material"} <= set(diag["grouping"]):
    lab = float(diag.loc[diag["grouping"] == "laboratory", "pc1_eta2"].iloc[0])
    mat = float(diag.loc[diag["grouping"] == "material", "pc1_eta2"].iloc[0])
    print()
    if n_multi == 0:
        print("SKIPPED: lab-vs-material comparison not meaningful with zero multi-provider")
        print("  properties (see the WARNING above) -- laboratory and method are too close")
        print("  to a bijection here for the comparison to isolate either one.")
    elif lab > mat:
        print("WARNING: PC1 tracks the laboratory more than the material.")
        print("The embedding is encoding provenance; treat the index as unusable")
        print("until the concentration ranges are harmonised.")
    else:
        print("PC1 tracks the material more than the laboratory, as it should.")

# --- the check that actually bears on usability: same material, different measurement ---
# eta-squared on cluster/PC1 answers "what does the dominant direction of variance track",
# which is confounded exactly when method predicts laboratory (the case here). The direct
# question is retrieval: within one assay method, is a same-material pair of properties
# closer than a different-material pair? This does not need >=2 providers on any single
# property -- it only needs the same material measured more than once under the same
# method, e.g. by different laboratories or at different exposure times.
print("\nsame-material vs different-material distance, within one method:")
same_d, diff_d = [], []
rng = np.random.default_rng(0)
for method, group in df.dropna(subset=["substance", "method"]).groupby("method"):
    if len(group) < 4:
        continue
    idx = group.index.to_numpy()
    if len(idx) > 400:  # cap the O(n^2) pair count per method
        idx = rng.choice(idx, 400, replace=False)
    Xg = df.loc[idx, vector_cols].to_numpy(dtype=float)
    subs = df.loc[idx, "substance"].to_numpy()
    D = np.sqrt(((Xg[:, None, :] - Xg[None, :, :]) ** 2).sum(-1))
    iu, ju = np.triu_indices(len(idx), k=1)
    same = subs[iu] == subs[ju]
    if 0 < same.sum() < len(same):
        same_d.append(D[iu, ju][same])
        diff_d.append(D[iu, ju][~same])

if same_d:
    same_d, diff_d = np.concatenate(same_d), np.concatenate(diff_d)
    combined = np.concatenate([same_d, diff_d])
    ranks = pd.Series(combined).rank().to_numpy()
    auc = 1 - (ranks[: len(same_d)].sum() - len(same_d) * (len(same_d) + 1) / 2) / (
        len(same_d) * len(diff_d)
    )
    print("  median same-material distance: {:.3f} decades (n={} pairs)".format(
        float(np.median(same_d)), len(same_d)))
    print("  median diff-material distance: {:.3f} decades (n={} pairs)".format(
        float(np.median(diff_d)), len(diff_d)))
    print("  AUC (P[same-material pair is closer]): {:.3f}  (0.5 = chance, 1.0 = perfect)".format(auc))
    if np.median(same_d) < 1e-6 and np.median(diff_d) < 1e-6:
        print("  WARNING: both medians are ~0 -- most vectors are near-identical regardless")
        print("  of material. Check the mode-collapse diagnostic above before trusting AUC.")
else:
    print("  not enough same-method, multi-material data for this check")

# --- cluster composition: does it make sense? --------------------------------------------
print("\ncluster vs n_determined (rows = cluster, cols = how many benchmark responses "
      "were actually reached) -- a cluster that is just one n_determined value is an")
print("artefact of censoring, not a biological grouping:")
print(pd.crosstab(df["cluster"], df["n_determined"]).to_string())

summary = (
    df.groupby("cluster")
    .agg(
        n=("id", "size"),
        n_materials=("substance", "nunique"),
        n_laboratories=("providers", "nunique"),
        median_n_providers=("n_providers", "median"),
        median_n_determined=("n_determined", "median"),
        methods=("method", lambda s: "|".join(sorted(set(s.dropna().astype(str))))[:80]),
    )
    .reset_index()
)
print("\ncluster composition:")
print(summary.to_string(index=False))


def top_n(series, n=6):
    counts = series.dropna().astype(str).value_counts()
    return ", ".join("{} ({})".format(v, c) for v, c in counts.head(n).items())


print("\ncluster contents (top materials / endpoints / methods by count):")
top_terms = []
for cluster_id, group in df.groupby("cluster"):
    print("\ncluster {} -- n={}, {} materials, {} laboratories".format(
        cluster_id, len(group), group["substance"].nunique(), group["providers"].nunique()))
    print("  materials:            " + top_n(group["substance"]))
    print("  endpoints:            " + top_n(group["endpoint"]))
    print("  methods:              " + top_n(group["method"], n=4))
    print("  concentration units:  " + top_n(group["concentration_unit"], n=4))
    for kind, col in (("material", "substance"), ("endpoint", "endpoint"),
                      ("method", "method"), ("concentration_unit", "concentration_unit")):
        for value, count in group[col].dropna().astype(str).value_counts().head(10).items():
            top_terms.append({"cluster": cluster_id, "kind": kind, "value": value, "count": count})

# --- outputs ------------------------------------------------------------------------------
summary.to_csv(product["data"], index=False)
print("\nwrote", len(summary), "rows to", product["data"])

pd.DataFrame(top_terms).to_csv(product["data_top"], index=False)
print("wrote", len(top_terms), "rows to", product["data_top"])

fig = px.scatter(
    df,
    x="pc1",
    y="pc2",
    color=df["cluster"].astype(str),
    symbol="endpointcategory_s" if "endpointcategory_s" in df.columns else None,
    hover_data=[c for c in ("substance", "method", "endpoint", "providers", "n_determined")
                if c in df],
    labels={"color": "cluster", "pc1": "PC1 (decades)", "pc2": "PC2 (decades)"},
    title="BMD vectors: {} properties, {} clusters".format(len(df), k),
)
fig.update_layout(
    font=dict(family="Georgia, 'Times New Roman', serif", color="#0b0b0b", size=13),
    paper_bgcolor="#fcfcfb",
    plot_bgcolor="#fcfcfb",
)
fig.update_xaxes(showline=True, linecolor="#898781", gridcolor="#e1e0d9", zeroline=False)
fig.update_yaxes(showline=True, linecolor="#898781", gridcolor="#e1e0d9", zeroline=False)
# No separate file: product["nb"] is .html, so the executed notebook -- this figure
# included, as its last-expression output -- IS the report.
fig
