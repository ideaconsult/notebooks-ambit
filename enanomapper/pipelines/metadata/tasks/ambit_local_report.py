# + tags=["parameters"]
ambit_base_url = "http://localhost:9090/ambit2"
owner_name = "NanoGenotox"
product = None
upstream = None
# -

# Paper-style report for a LIVE local AMBIT instance.
#
# Queries a running AMBIT (default http://localhost:9090/ambit2) over its REST API — the same
# instance the import test populates — and renders publication-quality figures of the imported
# genotoxicity data, so a freshly-imported database can be eyeballed the way it would appear in
# a paper (the AMBIT source of truth, before Solr/metaenm indexing).
#
# Ploomber renders this task's notebook to HTML (product.nb = ...html), so the figures below
# are just shown inline — no manual HTML assembly needed.
#
# Figures:
#   1. Study inventory by assay method (COMET / MICRONUCLEUS / COMET FPG / MLA / ...).
#   2. Dose-response: MNBNC frequency (micronucleus) and % DNA in tail (comet) vs concentration,
#      one line per material — the core genotox read-out.
#   3. Control coverage: per method, how many protocol applications carry a positive / negative
#      (0-dose) control point — the interpretability story this curation exercise is about.
#
# Colours use the validated data-viz categorical palette (blue/aqua/yellow/green; CVD worst
# adjacent ΔE 24.2). Sub-3:1 hues are always paired with a legend + direct labels (relief rule).

import json
import urllib.request
from collections import Counter, defaultdict

import numpy as np
import matplotlib.pyplot as plt

# --- validated palette (dataviz references/palette.md) --------------------------------------
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
CAT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
GOOD = "#0ca30c"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": "#c3c2b7",
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "font.size": 11,
})


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def method_of(pa):
    g = pa.get("protocol", {}).get("guideline", [])
    return (g[0] if g else "?") or "?"


def cond_num(conditions, key):
    v = conditions.get(key)
    if isinstance(v, dict):
        v = v.get("loValue")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- gather everything from live AMBIT in one pass ------------------------------------------
base = ambit_base_url.rstrip("/")
print("querying live AMBIT:", base, "| owner:", owner_name)
subs = fetch("{}/substance?media=application/json&pagesize=1000".format(base)).get("substance", [])
if owner_name:
    subs = [s for s in subs if s.get("ownerName") == owner_name]
print("substances:", len(subs))

method_studies = Counter()
dr = {"MNBNC_FREQUENCY": defaultdict(list), "DNA_STRAND_BREAKS": defaultdict(list)}
ctrl = defaultdict(lambda: {"papps": set(), "with_pos": set(), "with_neg": set()})

for s in subs:
    pn = s.get("publicname") or s.get("name") or "?"
    studies = fetch("{}/substance/{}/study?media=application/json".format(base, s["i5uuid"])).get("study", [])
    for pa in studies:
        m = method_of(pa)
        method_studies[m] += 1
        pid = pa.get("uuid")
        ctrl[m]["papps"].add(pid)
        for e in pa.get("effects", []):
            ep = e.get("endpoint")
            conds = e.get("conditions", {})
            dose = cond_num(conds, "CONCENTRATION")
            val = e.get("result", {}).get("loValue")
            mat = str(conds.get("MATERIAL", "")).lower()
            if "positive" in mat:
                ctrl[m]["with_pos"].add(pid)
            if dose == 0.0 or mat in ("control", "solvent_control", "control_negative"):
                ctrl[m]["with_neg"].add(pid)
            if ep in dr and dose is not None and val is not None and not pn.upper().startswith("CONTROL"):
                try:
                    dr[ep][pn].append((dose, float(val)))
                except (TypeError, ValueError):
                    pass

n_papps = sum(method_studies.values())
print("protocol applications:", n_papps, "| studies by method:", dict(method_studies))

# ============================================================================================
# Figure 1 — study inventory by assay method
# ============================================================================================
items = method_studies.most_common()
labels = [k for k, _ in items]
vals = [v for _, v in items]
fig, ax = plt.subplots(figsize=(7.2, 0.5 * len(labels) + 1.2))
bars = ax.barh(range(len(labels)), vals, color=[CAT[i % len(CAT)] for i in range(len(labels))],
               height=0.62, zorder=3)
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels)
ax.invert_yaxis()
ax.set_xlabel("protocol applications (studies)")
ax.set_title("Study inventory by assay method", loc="left", fontweight="bold", pad=10)
ax.grid(axis="y", visible=False)
for b, v in zip(bars, vals):
    ax.text(b.get_width() + max(vals) * 0.01, b.get_y() + b.get_height() / 2, str(v),
            va="center", ha="left", color=INK2, fontsize=10)
ax.margins(x=0.12)
plt.show()


# ============================================================================================
# Figure 2 — dose-response per material (the two flagship endpoints)
# ============================================================================================
def dose_response(endpoint, ylabel, title):
    """Small multiples — one panel per material. Overlaying many materials on one axis is
    unreadable (dose grids differ, medians zigzag); a panel grid with a shared y-scale lets
    each dose-response curve be read on its own while staying comparable. Points are the raw
    replicate values (grey) with the per-dose median line (blue) on top."""
    by_mat = {k: sorted(v) for k, v in dr[endpoint].items() if len(v) >= 4}
    if not by_mat:
        print("no dose-response data for", endpoint)
        return
    # rank materials by how much signal they show (max median), keep the top 9 for a 3x3 grid
    def peak(pts):
        agg = defaultdict(list)
        for d, v in pts:
            agg[d].append(v)
        return max(float(np.median(vs)) for vs in agg.values())
    mats = sorted(by_mat, key=lambda m: peak(by_mat[m]), reverse=True)[:9]
    ymax = max(v for m in mats for _, v in by_mat[m]) * 1.05
    ncol = 3
    nrow = (len(mats) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(9.6, 2.7 * nrow), sharex=True, sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for i, mat in enumerate(mats):
        ax = axes[i]
        agg = defaultdict(list)
        for d, v in by_mat[mat]:
            agg[d].append(v)
        # raw replicate points, recessive
        rx = [d for d, _ in by_mat[mat]]
        ry = [v for _, v in by_mat[mat]]
        ax.scatter(rx, ry, s=10, color=MUTED, alpha=0.35, zorder=2, edgecolors="none")
        # per-dose median line
        xs = sorted(agg)
        ys = [float(np.median(agg[x])) for x in xs]
        ax.plot(xs, ys, marker="o", ms=4, lw=2, color=CAT[0], zorder=3,
                markeredgecolor=SURFACE, markeredgewidth=1.0)
        ax.set_xscale("symlog", linthresh=0.5)
        ax.set_ylim(0, ymax)
        ax.set_title(mat, loc="left", fontsize=10, color=INK2)
    for j in range(len(mats), len(axes)):
        axes[j].set_visible(False)
    for k in range(len(mats)):
        if k % ncol == 0:
            axes[k].set_ylabel(ylabel)
        if k >= len(mats) - ncol:
            axes[k].set_xlabel("conc. (µg/cm²)")
    fig.suptitle(title, x=0.02, ha="left", fontweight="bold", fontsize=13, y=1.0)
    extra = len(by_mat) - len(mats)
    note = "grey = replicate values · blue = per-dose median"
    if extra > 0:
        note += "   ·   +{} more materials".format(extra)
    fig.text(0.02, -0.01, note, ha="left", color=MUTED, fontsize=9)
    fig.tight_layout()
    plt.show()


dose_response("MNBNC_FREQUENCY", "MNBNC frequency", "Micronucleus dose–response (median per dose)")
dose_response("DNA_STRAND_BREAKS", "% DNA in tail", "Comet dose–response (median per dose)")

# ============================================================================================
# Figure 3 — control coverage per method
# ============================================================================================
methods = [m for m, _ in method_studies.most_common() if len(ctrl[m]["papps"]) >= 5]
if methods:
    total = [len(ctrl[m]["papps"]) for m in methods]
    pos = [len(ctrl[m]["with_pos"]) for m in methods]
    neg = [len(ctrl[m]["with_neg"]) for m in methods]
    x = np.arange(len(methods))
    w = 0.26
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.bar(x - w, total, w, label="all studies", color=CAT[0], zorder=3)
    ax.bar(x, pos, w, label="with positive control", color=GOOD, zorder=3)
    ax.bar(x + w, neg, w, label="with negative (0-dose)", color=CAT[2], zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=20, ha="right")
    ax.set_ylabel("protocol applications")
    ax.set_title("Control coverage by assay method", loc="left", fontweight="bold", pad=10)
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2)
    plt.show()

# Ploomber needs a data product; write a tiny summary CSV alongside the rendered notebook.
import csv
with open(product["data"], "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f)
    wr.writerow(["method", "protocol_applications", "with_positive_control", "with_negative_0dose"])
    for m, _ in method_studies.most_common():
        wr.writerow([m, len(ctrl[m]["papps"]), len(ctrl[m]["with_pos"]), len(ctrl[m]["with_neg"])])
print("wrote", product["data"])
