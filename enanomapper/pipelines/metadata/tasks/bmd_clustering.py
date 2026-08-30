# + tags=["parameters"]
upstream = ["bmd_embedding"]
n_clusters = "auto"    # an int to fix k, or "auto" to pick it by silhouette score
k_min = 2
k_max = 20
product = None
# -

# Cluster the BMD vectors.
#
# The vectors are BMD CDFs flattened, in log10 concentration, so Euclidean distance
# between two of them is an RMS displacement in decades -- which is what makes plain
# k-means meaningful here in a way it would not be on an arbitrary embedding: a cluster is
# a set of properties whose benchmark concentrations agree to within some number of
# decades.
#
# This task only clusters. What the clusters actually track -- material, method,
# laboratory, or an artefact of undetermined BMDs -- is bmd_cluster_analysis.py's job,
# kept in a separate task so a new diagnostic there never requires re-running k-means or
# re-fetching from AMBIT: it reads this task's (small) output, not the other way round.

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

df = pd.read_csv(upstream["bmd_embedding"]["data_csv"])
print("properties:", len(df))
if df.empty:
    raise SystemExit("no BMD vectors to cluster - run bmd_embedding first")

vector_cols = sorted(c for c in df.columns if c.startswith("v") and c[1:].isdigit())
X = df[vector_cols].to_numpy(dtype=float)
print("vector dimension:", X.shape[1])

# --- how many clusters -------------------------------------------------------------------
# Picked by silhouette score, which rewards clusters that are both internally tight and
# separated from their neighbours, over a small swept range. An operator can still fix k
# by passing an int for n_clusters.
if isinstance(n_clusters, str) and n_clusters == "auto":
    upper = min(k_max, len(df) - 1)
    print("\nchoosing k by silhouette score (k = {}..{}):".format(k_min, upper))
    trials = {}
    for k_try in range(k_min, upper + 1):
        trial_labels = KMeans(n_clusters=k_try, n_init=10, random_state=0).fit_predict(X)
        score = silhouette_score(X, trial_labels, sample_size=min(2000, len(df)), random_state=0)
        trials[k_try] = (trial_labels, score)
        print("  k={:<3} silhouette={:.4f}".format(k_try, score))
    k = max(trials, key=lambda kk: trials[kk][1])
    labels = trials[k][0]
    print("selected k={} (silhouette={:.4f})".format(k, trials[k][1]))
else:
    k = int(min(int(n_clusters), max(2, len(df) // 2)))
    print("\nusing fixed k={} (n_clusters parameter)".format(k))
    labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
df["cluster"] = labels

# Two components purely for the picture downstream; the clustering itself uses the full
# vector, not these two.
coords = PCA(n_components=2, random_state=0).fit_transform(X)
df["pc1"], df["pc2"] = coords[:, 0], coords[:, 1]

print("\ncluster sizes:")
print(df.groupby("cluster").size().to_string())

# Carry the identifying columns through so bmd_cluster_analysis.py can read this file alone
# for anything that doesn't need the raw 96-d vector (which stays in bmd_embedding's own
# output -- duplicating it here would desync the two the moment either is regenerated).
out_cols = [
    c
    for c in (
        "id", "cluster", "pc1", "pc2",
        "substance", "s_uuid_s", "endpointcategory_s", "method", "endpoint", "hours",
        "concentration_unit", "providers", "n_providers", "n_determined", "control_route",
    )
    if c in df.columns
]
df[out_cols].to_csv(product["data"], index=False)
print("\nwrote", len(df), "rows to", product["data"])
