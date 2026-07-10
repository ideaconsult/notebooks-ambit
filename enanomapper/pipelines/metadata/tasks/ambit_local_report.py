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


def cond_unit(conditions, key):
    v = conditions.get(key)
    return str(v.get("unit")) if isinstance(v, dict) and v.get("unit") else None


# --- gather everything from live AMBIT in one pass ------------------------------------------
base = ambit_base_url.rstrip("/")
print("querying live AMBIT:", base, "| owner:", owner_name)
subs = fetch("{}/substance?media=application/json&pagesize=1000".format(base)).get("substance", [])
if owner_name:
    subs = [s for s in subs if s.get("ownerName") == owner_name]
print("substances:", len(subs))

method_studies = Counter()
owner_studies = Counter()   # citation.owner = the lab / institute that produced the study
cell_studies = Counter()    # E.cell_type = the cell line
# dose-response is discovered, NOT hardcoded per assay. Each point keeps its cell line, data
# owner, material and control role, so the figure can facet by cell, colour by owner, and mark
# controls distinctly — and it works for ANY assay in ANY AMBIT instance.
dr = defaultdict(list)      # endpoint -> [ {cell, owner, material, dose, value, role}, ... ]
dr_units = defaultdict(Counter)      # endpoint -> value-unit Counter (read from data)
dr_dose_units = defaultdict(Counter)  # endpoint -> concentration-unit Counter (read from data)
ctrl = defaultdict(lambda: {"papps": set(), "with_pos": set(), "with_neg": set()})


def owner_of(pa):
    o = (pa.get("citation", {}) or {}).get("owner")
    return str(o) if o else "?"


def cell_of(pa):
    p = pa.get("parameters", {}) or {}
    c = p.get("E.cell_type") or p.get("E.CELL_TYPE")
    return str(c) if c else "?"


def control_role(material, dose):
    """positive / negative / sample from the treatment material token (+ 0-dose => negative)."""
    m = material.lower()
    if "positive" in m:
        return "positive"
    if dose == 0.0 or m in ("control", "solvent_control", "control_negative", "vehicle"):
        return "negative"
    return "sample"


for s in subs:
    pn = s.get("publicname") or s.get("name") or "?"
    studies = fetch("{}/substance/{}/study?media=application/json".format(base, s["i5uuid"])).get("study", [])
    for pa in studies:
        m = method_of(pa)
        cell = cell_of(pa)
        owner = owner_of(pa)
        method_studies[m] += 1
        owner_studies[owner] += 1
        cell_studies[cell] += 1
        pid = pa.get("uuid")
        ctrl[m]["papps"].add(pid)
        for e in pa.get("effects", []):
            ep = e.get("endpoint")
            conds = e.get("conditions", {})
            dose = cond_num(conds, "CONCENTRATION")
            result = e.get("result", {}) or {}
            val = result.get("loValue")
            mat = str(conds.get("MATERIAL", ""))
            role = control_role(mat, dose)
            if role == "positive":
                ctrl[m]["with_pos"].add(pid)
            if role == "negative":
                ctrl[m]["with_neg"].add(pid)
            # record EVERY numeric endpoint that has a concentration axis — endpoints are
            # discovered from the data, not assumed (works for arbitrary assays). Controls are
            # kept (role != sample) so they can be drawn on the same axes as the samples.
            if ep and dose is not None and val is not None:
                try:
                    dr[ep].append({"cell": cell, "owner": owner, "material": pn,
                                   "dose": dose, "value": float(val), "role": role})
                    if result.get("unit"):
                        dr_units[ep][str(result["unit"])] += 1
                    du = cond_unit(conds, "CONCENTRATION")
                    if du:
                        dr_dose_units[ep][du] += 1
                except (TypeError, ValueError):
                    pass

n_papps = sum(method_studies.values())
print("protocol applications:", n_papps, "| studies by method:", dict(method_studies))

# ============================================================================================
# Figures 1-3 — study inventory by assay method, by data owner (lab), and by cell line
# ============================================================================================
def inventory_bar(counter, title, single_hue=None, top=None):
    """One horizontal bar chart: counts per category, most-frequent first, direct-labelled.
    single_hue keeps an identity dimension one colour (a bar chart's bars are one series);
    method/owner/cell each get their own hue so the three panels read as distinct facets."""
    items = counter.most_common(top)
    labels = [k for k, _ in items]
    vals = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(7.4, 0.42 * len(labels) + 1.2))
    color = single_hue or CAT[0]
    bars = ax.barh(range(len(labels)), vals, color=color, height=0.64, zorder=3)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("protocol applications (studies)")
    ax.set_title(title, loc="left", fontweight="bold", pad=10)
    ax.grid(axis="y", visible=False)
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + max(vals) * 0.01, b.get_y() + b.get_height() / 2, str(v),
                va="center", ha="left", color=INK2, fontsize=10)
    ax.margins(x=0.14)
    plt.show()


inventory_bar(method_studies, "Study inventory by assay method", single_hue=CAT[0])
inventory_bar(owner_studies, "Studies by data owner (lab / institute)", single_hue=CAT[1])
inventory_bar(cell_studies, "Studies by cell line", single_hue=CAT[2], top=15)


# ============================================================================================
# Dose-response — endpoints DISCOVERED from the data (not hardcoded), so this works for any
# assay. Each endpoint is drawn as small multiples FACETED BY CELL LINE, with sample lines
# one line per material with its data owner in the label, and the controls marked distinctly
# (positive = red X, negative = grey o) on the same axes — so owner, cell line and controls are
# all visible on the data chart, and materials are never merged.
# ============================================================================================
def endpoint_label(ep):
    units = dr_units.get(ep)
    unit = units.most_common(1)[0][0] if units else None
    pretty = ep.replace("_", " ").title()
    return "{} ({})".format(pretty, unit) if unit else pretty


def dose_label(ep):
    """x-axis label with the concentration unit READ FROM THE DATA (not hardcoded)."""
    units = dr_dose_units.get(ep)
    unit = units.most_common(1)[0][0] if units else None
    return "concentration ({})".format(unit) if unit else "concentration"


def pick_dose_response_endpoints(max_endpoints=4, min_points=12, min_doses=3):
    """Endpoints that look like dose-responses: enough sample points across >= min_doses
    distinct concentrations. Ranked by (n sample points) then (distinct doses)."""
    scored = []
    for ep, recs in dr.items():
        samples = [r for r in recs if r["role"] == "sample"]
        doses = {round(r["dose"], 6) for r in samples}
        if len(samples) >= min_points and len(doses) >= min_doses:
            scored.append((len(samples), len(doses), ep))
    scored.sort(reverse=True)
    return [ep for _, _, ep in scored[:max_endpoints]]


CTRL_POS = "#d03b3b"   # status critical red — positive control
CTRL_NEG = MUTED       # grey — negative / 0-dose control


def _material_median(recs):
    """Per-dose median across ONE material's replicate points -> (xs, ys). Only a single
    material's records are ever passed in — materials are NEVER averaged together."""
    agg = defaultdict(list)
    for r in recs:
        agg[r["dose"]].append(r["value"])
    xs = sorted(agg)
    return xs, [float(np.median(agg[x])) for x in xs]


def dose_response(endpoint, max_materials_per_panel=6):
    recs = dr[endpoint]
    samples = [r for r in recs if r["role"] == "sample"]
    if not samples:
        print("no sample dose-response data for", endpoint)
        return
    ylabel = endpoint_label(endpoint)
    # facet by cell line: cells with the most sample points (up to a 3x3 grid)
    cells = [c for c, _ in Counter(r["cell"] for r in samples).most_common(9)]

    ncol = min(3, len(cells))
    nrow = (len(cells) + ncol - 1) // ncol
    # y-axis is INDEPENDENT per panel — response ranges differ a lot between cell lines, so a
    # shared scale flattens the low-response cells. x (concentration) stays shared for comparison.
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.6 * ncol, 3.0 * nrow),
                             sharex=True, sharey=False, squeeze=False)
    axes = axes.ravel()
    for i, cell in enumerate(cells):
        ax = axes[i]
        cell_recs = [r for r in recs if r["cell"] == cell]
        # ONE line per material (never merged); keep the materials with the most points.
        by_mat = defaultdict(list)
        owner_of_mat = {}
        for r in cell_recs:
            if r["role"] == "sample":
                by_mat[r["material"]].append(r)
                owner_of_mat[r["material"]] = r["owner"]
        top_mats = [m for m, _ in Counter({m: len(v) for m, v in by_mat.items()}).most_common(
            max_materials_per_panel)]
        for j, mat in enumerate(top_mats):
            xs, ys = _material_median(by_mat[mat])
            ax.plot(xs, ys, marker="o", ms=3.5, lw=1.6, color=CAT[j % len(CAT)], zorder=3,
                    markeredgecolor=SURFACE, markeredgewidth=0.8,
                    label="{} ({})".format(mat, owner_of_mat.get(mat, "?")))
        # controls on the same axes, distinct marks
        pos = [r for r in cell_recs if r["role"] == "positive"]
        neg = [r for r in cell_recs if r["role"] == "negative"]
        if pos:
            ax.scatter([r["dose"] for r in pos], [r["value"] for r in pos], marker="X", s=42,
                       color=CTRL_POS, zorder=5, edgecolors=SURFACE, linewidths=0.8,
                       label="positive control")
        if neg:
            ax.scatter([r["dose"] for r in neg], [r["value"] for r in neg], marker="o", s=24,
                       facecolors="none", edgecolors=CTRL_NEG, linewidths=1.2, zorder=4,
                       label="negative (0-dose)")
        ax.set_xscale("symlog", linthresh=0.5)
        ax.set_ylim(bottom=0)  # dose-response floors at 0; top autoscales per panel
        n_extra = len(by_mat) - len(top_mats)
        ttl = cell if n_extra <= 0 else "{}  (+{} more materials)".format(cell, n_extra)
        ax.set_title(ttl, loc="left", fontsize=10, color=INK)
        # per-panel legend (materials differ per cell, so the legend must be per panel)
        ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="upper left",
                  handlelength=1.2, borderaxespad=0.2)
    for j in range(len(cells), len(axes)):
        axes[j].set_visible(False)
    for k in range(len(cells)):
        # y is independent per panel now, so label it on every panel (not just the left column)
        axes[k].set_ylabel(ylabel)
        if k >= len(cells) - ncol:
            axes[k].set_xlabel(dose_label(endpoint))
    fig.suptitle("Dose–response by cell line — {}  ·  one line per material (owner in label)".format(ylabel),
                 x=0.02, ha="left", fontweight="bold", fontsize=12, y=1.004)
    fig.text(0.02, -0.01, "each line = one material's per-dose median · red X = positive control · grey o = negative/0-dose",
             ha="left", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.01, 1, 1))
    plt.show()


dr_endpoints = pick_dose_response_endpoints()
print("dose-response endpoints (auto-selected):", dr_endpoints)
for ep in dr_endpoints:
    dose_response(ep)

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
