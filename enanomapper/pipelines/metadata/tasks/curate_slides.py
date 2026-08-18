# + tags=["parameters"]
upstream = ["curate_passing_*", "curate_failing_*", "viz_metadata"]
filter_project = None
product = None
# -

# Genotox curation — slide-deck report for domain-expert review.
#
# curate_passing.py / curate_failing.py already fetch and flatten the dose-response data and
# render it as ONE dropdown-driven Plotly dashboard per project per pass/fail split — efficient
# to build, but awkward for a linear expert review (hunt through a dropdown vs. paging through
# studies one at a time with full context in view).
#
# This task re-shapes the SAME already-computed data (read back from the CSVs those tasks
# wrote — no re-fetching from AMBIT) into a slide-deck-style HTML report: what was one dropdown
# OPTION becomes one SLIDE — a self-contained section with that study's dose-response plot(s)
# plus its metadata. Summary slide first, then passing studies, then failing studies; one deck
# per project (`products/slides_<project>.html`).

import tasks.genotox_curation_lib as lib

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- journal-style figure theme (validated data-viz categorical palette; see
# ambit_local_report.py) — white background, minimal gridlines, no boxed axes, direct-labeled
# traces preferred over a legend-only read. Applied to every figure below via apply_journal_style
# / CAT (trace colours cycle through this palette instead of Plotly's default set).
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
CAT = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]

JOURNAL_FONT = dict(family="Georgia, 'Times New Roman', serif", color=INK, size=13)


def apply_journal_style(fig, **layout_kwargs):
    """Restyle a Plotly figure to read like a journal dose-response figure: white/off-white
    background, thin muted gridlines, no top/right border, serif axis labels."""
    fig.update_layout(
        font=JOURNAL_FONT,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        colorway=CAT,
        legend=dict(bgcolor=SURFACE, bordercolor=GRID, borderwidth=1),
        **layout_kwargs,
    )
    fig.update_xaxes(showline=True, linecolor=MUTED, linewidth=1,
                      gridcolor=GRID, gridwidth=0.6, zeroline=False,
                      title_font=dict(color=INK2), tickfont=dict(color=MUTED))
    fig.update_yaxes(showline=True, linecolor=MUTED, linewidth=1,
                      gridcolor=GRID, gridwidth=0.6, zeroline=False,
                      title_font=dict(color=INK2), tickfont=dict(color=MUTED))
    return fig


passing_csv = upstream["curate_passing_*"][f"curate_passing_{filter_project}"]["data_csv"]
failing_csv = upstream["curate_failing_*"][f"curate_failing_{filter_project}"]["data_csv"]
viability_csv = str(passing_csv).replace(".csv", "_viability.csv")
readiness_csv = upstream["viz_metadata"]["data"]


def read_csv_or_empty(path):
    """curate_passing.py / curate_failing.py skip writing their CSV entirely when there's no
    data for that split (e.g. a project with zero failing studies) — pd.read_csv raises
    EmptyDataError on a missing/empty file rather than returning an empty frame, so guard it."""
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


passing = read_csv_or_empty(passing_csv)
failing = read_csv_or_empty(failing_csv)
viability = read_csv_or_empty(viability_csv)

readiness = read_csv_or_empty(readiness_csv)
if not readiness.empty:
    readiness = readiness[
        readiness["owner_name_s"].astype(str).str.casefold() == str(filter_project).casefold()
    ]

for df in (passing, failing, viability):
    if not df.empty and "E.cell_type_ss" in df.columns:
        df["E.cell_type_ss"] = df["E.cell_type_ss"].apply(lib.parse_csv_list)

print("passing rows:", len(passing), "| failing rows:", len(failing),
      "| viability rows:", len(viability), "| readiness rows:", len(readiness))

CRITERION_FLAGS = {
    "c_conc3": "at least 3 test concentrations",
    "c_neg":   "a negative control",
    "c_pos":   "a positive control",
    "c_viab":  "a paired cell-viability study",
}


# --- materials overview: one row per material, plain counts, no UUIDs ----------------------
# Mirrors what the slide deck actually shows a reviewer for a material — "how many genotox
# studies, how many viability studies are available for this material" — as one row they can
# read directly, instead of asking them to cross-reference document_uuid_s across two sheets.
# Genotox and viability are matched at the SAME granularity the plots use (same substance,
# s_uuid_s) — there is no true 1:1 study pairing (a material commonly has several viability
# studies for one genotox study), so this table deliberately reports COUNTS, not a merged row.
# Used both on the summary slide (HTML table) and as the first sheet of the .xlsx export.
def materials_overview(passing_df, viability_df, failing_df):
    if passing_df.empty and failing_df.empty:
        return pd.DataFrame()

    def counts(df, label_col="document_uuid_s"):
        if df.empty or "s_uuid_s" not in df.columns:
            return pd.Series(dtype=int)
        return df.drop_duplicates(label_col).groupby("s_uuid_s")[label_col].nunique()

    def material_names(df):
        if df.empty:
            return pd.Series(dtype=str)
        return (
            df.drop_duplicates("s_uuid_s")
            .set_index("s_uuid_s")["publicname_s"].fillna("(unnamed material)")
        )

    n_pass = counts(passing_df)
    n_fail = counts(failing_df)
    n_viab = counts(viability_df) if not viability_df.empty else pd.Series(dtype=int)
    names = material_names(passing_df)
    if not failing_df.empty:
        names = names.combine_first(material_names(failing_df))

    # brief per-material details (assays, cell types, exposure times, concentration ranges) —
    # pooled across passing + failing genotox rows, since a reviewer wants "what was tested on
    # this material" regardless of whether every study passed the readiness criteria.
    genotox_df = pd.concat([passing_df, failing_df], ignore_index=True) if (
        not passing_df.empty or not failing_df.empty) else pd.DataFrame()

    def joined_unique(df, col, s):
        if df.empty or col not in df.columns:
            return ""
        vals = df.loc[df["s_uuid_s"] == s, col].dropna()
        flat = set()
        for v in vals:
            items = v if isinstance(v, list) else [v]
            flat.update(str(x) for x in items if str(x) not in ("", "nan"))
        return ", ".join(sorted(flat))

    def conc_range(df, s):
        if df.empty or "dose" not in df.columns:
            return ""
        sub = df[(df["s_uuid_s"] == s) & df["dose"].notna()]
        if sub.empty:
            return ""
        units = sorted({str(u) for u in sub["dose_unit"].dropna().unique() if str(u) != "nan"})
        return "{:g} - {:g} {}".format(sub["dose"].min(), sub["dose"].max(), "/".join(units))

    s_uuids = sorted(set(n_pass.index) | set(n_fail.index))
    rows = [{
        "material": names.get(s, "(unnamed material)"),
        "passing genotox studies": int(n_pass.get(s, 0)),
        "failing genotox studies": int(n_fail.get(s, 0)),
        "cell-viability studies available": int(n_viab.get(s, 0)),
        "assays": joined_unique(genotox_df, "assay", s) or joined_unique(genotox_df, "E.method_s", s),
        "cell types": joined_unique(genotox_df, "E.cell_type_ss", s),
        "exposure time": joined_unique(genotox_df, "exposure_time", s),
        "concentration range": conc_range(genotox_df, s),
    } for s in s_uuids]
    return pd.DataFrame(rows).sort_values("material").reset_index(drop=True)


def _endpoint_unit_groups(sdf):
    """Distinct (endpoint, dose_unit, response_unit) combinations with real dose-response
    points, in first-seen order. Each becomes its own sub-panel — different endpoints/units are
    not comparable on one axis, and a slide (unlike the shared dropdown dashboards) can afford
    a dynamic per-study grid since it isn't reused across studies via visibility toggling."""
    pts = sdf[sdf["dose"].notna() & sdf["response"].notna() & sdf["control_label"].isna()]
    if pts.empty:
        return []
    keys = pts[["endpoint", "dose_unit", "response_unit"]].drop_duplicates()
    return list(keys.itertuples(index=False, name=None))


def one_study_figure(sdf, viab_sdf=None):
    """Build a standalone figure for ONE study: one row per distinct (endpoint, dose_unit,
    response_unit) combination present, genotox in the left column and paired cell-viability
    (same grouping) in the right column — never overlaying series with different units on one
    axis. All traces visible (no dropdown; the slide itself is the selector). Journal-styled:
    white background, thin axis lines, muted gridlines, palette-cycled trace colours."""
    gen_groups = _endpoint_unit_groups(sdf)
    via_groups = _endpoint_unit_groups(viab_sdf) if viab_sdf is not None else []
    n_rows = max(len(gen_groups), len(via_groups), 1)

    titles = []
    for i in range(n_rows):
        gt = "{} ({})".format(gen_groups[i][0], gen_groups[i][2]) if i < len(gen_groups) else ""
        vt = "{} ({})".format(via_groups[i][0], via_groups[i][2]) if i < len(via_groups) else ""
        titles.extend([gt, vt])

    fig = make_subplots(rows=n_rows, cols=2, subplot_titles=titles,
                         vertical_spacing=min(0.15, 0.6 / max(n_rows, 1)))

    def _panel(all_df, groups, row, col):
        endpoint, du, ru = groups[row - 1]
        subset = all_df[
            (all_df["endpoint"] == endpoint) & (all_df["dose_unit"] == du)
            & (all_df["response_unit"] == ru)
        ]
        # keep this panel's own controls (control_label rows have no endpoint to match on)
        ctrl = all_df[all_df["control_label"].notna()]
        lib._add_study_traces(fig, pd.concat([subset, ctrl]), visible0=True, row=row, col=col)
        fig.update_xaxes(title_text="dose ({})".format(du or "?"), type="log", row=row, col=col)
        fig.update_yaxes(title_text=str(ru or "?"), row=row, col=col)

    for i in range(len(gen_groups)):
        _panel(sdf, gen_groups, i + 1, 1)
    for i in range(len(via_groups)):
        _panel(viab_sdf, via_groups, i + 1, 2)

    fig.update_layout(showlegend=True, height=max(320, 260 * n_rows), margin=dict(t=40, b=20))
    apply_journal_style(fig)
    for ann in fig.layout.annotations:
        ann.font = dict(family=JOURNAL_FONT["family"], color=INK, size=13)
    return fig


def meta_row(sdf):
    """First row of a study's slice — carries the per-study metadata columns."""
    return sdf.iloc[0]


def meta_table(pairs):
    rows = "".join(
        "<tr><th style='text-align:left;padding:4px 12px 4px 0'>{}</th>"
        "<td style='padding:4px'>{}</td></tr>".format(lib.esc(k), v)
        for k, v in pairs if v not in (None, "", "nan")
    )
    return "<table style='font-family:sans-serif'>{}</table>".format(rows)


def link(url, text):
    return "<a href='{}' target='_blank'>{}</a>".format(lib.esc(url), lib.esc(text))


# enanomapper.adma.ai project slugs mostly match the AMBIT path segment
# (apps.ideaconsult.net/<slug>/...) from genotox_curation_lib.TAG_DBS_AMBIT, but not always —
# confirmed exception: AMBIT's "nanoreg1" is adma.ai's "nanoreg". Add further overrides here as
# they're found rather than assuming the AMBIT path is always right.
ADMA_SLUG_OVERRIDES = {
    "nanoreg1": "nanoreg",
}


def adma_url(s_uuid, substance_url):
    """enanomapper.adma.ai viewer link for a substance: /projects/<slug>/study/
    ?substanceUri=<url-encoded AMBIT substance URL>."""
    import urllib.parse

    if not s_uuid or not substance_url:
        return None
    tag = s_uuid.split("-")[0] if "-" in s_uuid else s_uuid
    ambit_base = lib.TAG_DBS_AMBIT.get(tag)
    if not ambit_base:
        return None
    slug = ambit_base.rstrip("/").rsplit("/", 1)[-1]
    slug = ADMA_SLUG_OVERRIDES.get(slug, slug)
    return "https://enanomapper.adma.ai/projects/{}/study/?substanceUri={}".format(
        slug, urllib.parse.quote(substance_url, safe="")
    )


def links_html(r):
    """Both the bare AMBIT substance link and the enanomapper.adma.ai study-viewer link."""
    substance_url = r.get("substance_url")
    parts = [link(substance_url, "substance"), link(r.get("study_url"), "raw JSON")]
    adma = adma_url(r.get("s_uuid_s"), substance_url)
    if adma:
        parts.append(link(adma, "enanomapper.adma.ai"))
    return " &nbsp; ".join(parts)


slide_sections = []
toc_entries = []
slide_id = 0


def add_slide(title, body_html, anchor_label=None):
    global slide_id
    slide_id += 1
    anchor = "slide-{}".format(slide_id)
    nav = "<p style='font-family:sans-serif'>{prev}<a href='#toc'>&uarr; contents</a> {next}</p>"
    slide_sections.append(
        "<section id='{anchor}' style='min-height:90vh;padding:2em;"
        "border-bottom:1px solid #ccc'>"
        "<h2 style='font-family:sans-serif'>{title}</h2>"
        "{body}"
        "{navtop}"
        "</section>".format(
            anchor=anchor, title=lib.esc(title), body=body_html,
            navtop=nav.format(prev="", next=""),
        )
    )
    if anchor_label:
        toc_entries.append((anchor, anchor_label))
    return anchor


# ================================================================================================
# 1. SUMMARY SLIDE (first)
# ================================================================================================
n_passing = passing["document_uuid_s"].nunique() if not passing.empty else 0
n_failing = failing["document_uuid_s"].nunique() if not failing.empty else 0

by_assay = (
    passing.drop_duplicates("document_uuid_s").groupby("assay").size()
    if not passing.empty and "assay" in passing.columns else pd.Series(dtype=int)
)
assay_rows = "".join(
    "<li>{}: {}</li>".format(lib.esc(a), n) for a, n in by_assay.items()
)

legend_rows = "".join(
    "<li><b>{}</b> — {}</li>".format(lib.esc(flag), lib.esc(desc))
    for flag, desc in CRITERION_FLAGS.items()
)

# --- NR2/EFSA interpretability funnel (same steps as viz_metadata.py's) --------------------
# cumulative survival through the 4 criteria, computed from this project's readiness rows.
funnel_html = ""
if not readiness.empty and {"c_conc3", "c_neg", "c_pos", "interpretable"} <= set(readiness.columns):
    funnel_steps = [
        ("All COMET/MN studies", len(readiness)),
        ("≥ 3 concentrations", int(readiness["c_conc3"].sum())),
        ("+ negative control",
         int((readiness["c_conc3"] & readiness["c_neg"]).sum())),
        ("+ positive control",
         int((readiness["c_conc3"] & readiness["c_neg"] & readiness["c_pos"]).sum())),
        ("+ paired viability", int(readiness["interpretable"].sum())),
    ]
    funnel_df = pd.DataFrame(funnel_steps, columns=["criterion", "studies"])
    funnel_fig = go.Figure(go.Funnel(
        y=funnel_df["criterion"], x=funnel_df["studies"],
        textinfo="value+percent initial",
        marker=dict(color=CAT[0]),
        connector=dict(line=dict(color=GRID, width=1)),
    ))
    apply_journal_style(
        funnel_fig,
        title=dict(text="NR2 interpretability funnel — {}".format(filter_project),
                    font=dict(family=JOURNAL_FONT["family"], color=INK, size=16)),
        height=420, margin=dict(t=60, b=20),
    )
    funnel_html = funnel_fig.to_html(full_html=False, include_plotlyjs=False)

# --- materials overview table (plain, no UUIDs) --------------------------------------------
overview_df = materials_overview(passing, viability, failing)
overview_html = ""
if not overview_df.empty:
    overview_cols = [
        "material", "passing genotox studies", "failing genotox studies",
        "cell-viability studies available", "assays", "cell types",
        "exposure time", "concentration range",
    ]
    overview_rows = "".join(
        "<tr>" + "".join(
            "<td style='padding:4px 12px'>{}</td>".format(lib.esc(row[c]))
            for c in overview_cols
        ) + "</tr>"
        for _, row in overview_df.iterrows()
    )
    overview_header = "".join(
        "<th style='text-align:left;padding:4px 12px'>{}</th>".format(lib.esc(c))
        for c in overview_cols
    )
    overview_html = (
        "<div style='font-family:sans-serif'>"
        "<b>Materials overview</b>"
        "<table style='border-collapse:collapse;margin-top:0.5em;font-size:0.9em'>"
        "<tr>" + overview_header + "</tr>"
        + overview_rows + "</table></div>"
    )

summary_body = """
<p style='font-family:sans-serif'>
Project <b>{project}</b>: <b>{n_pass}</b> interpretable (passing) studies,
<b>{n_fail}</b> studies failing at least one interpretability criterion.
</p>
{funnel_html}
{overview_html}
<div style='font-family:sans-serif'>
<b>Passing studies by assay:</b>
<ul>{assay_rows}</ul>
</div>
<div style='font-family:sans-serif'>
<b>A study is "interpretable" (passing) when it has:</b>
<ul>{legend_rows}</ul>
</div>
<details id='toc' style='font-family:sans-serif' open>
<summary style='cursor:pointer'><b>Contents</b></summary>
<ol>{{toc}}</ol>
</details>
""".format(project=lib.esc(filter_project), n_pass=n_passing, n_fail=n_failing,
           funnel_html=funnel_html, overview_html=overview_html,
           assay_rows=assay_rows, legend_rows=legend_rows)

add_slide("Summary — {}".format(filter_project), summary_body)
summary_slide_index = 0  # filled into {{toc}} placeholder after all slides are built

# ================================================================================================
# 2. ONE SLIDE PER PASSING STUDY
# ================================================================================================
if not passing.empty:
    docs = list(dict.fromkeys(passing["document_uuid_s"]))
    for doc in docs:
        sdf = passing[passing["document_uuid_s"] == doc]
        r = meta_row(sdf)
        viab_sdf = None
        if not viability.empty and "s_uuid_s" in viability.columns:
            viab_sdf = viability[viability["s_uuid_s"] == r["s_uuid_s"]]

        fig = one_study_figure(sdf, viab_sdf)
        plot_html = fig.to_html(full_html=False, include_plotlyjs=False)

        flags_met = ", ".join(
            desc for flag, desc in CRITERION_FLAGS.items()
            if flag in sdf.columns and bool(r.get(flag))
        )
        meta_html = meta_table([
            ("material", lib.esc(r.get("publicname_s"))),
            ("method", lib.esc(r.get("E.method_s"))),
            ("cell type", lib.esc(r.get("E.cell_type_ss"))),
            ("exposure time", lib.esc(r.get("exposure_time"))),
            ("owner / project", lib.esc(r.get("owner_name_s"))),
            ("reference", "{} ({})".format(
                lib.esc(r.get("reference_s")), lib.esc(r.get("reference_year_s")))),
            ("criteria met", lib.esc(flags_met)),
            ("source file", lib.esc(r.get("input_file"))),
            ("document uuid", "<span style='font-family:monospace;user-select:all'>{}</span>"
                               .format(lib.esc(r.get("document_uuid_s")))),
            ("links", links_html(r)),
        ])

        label = "{} | {} | {}".format(
            r.get("publicname_s"), r.get("E.method_s"), r.get("E.cell_type_ss"))
        add_slide(
            "PASS — {}".format(label),
            plot_html + meta_html,
            anchor_label="PASS — {}".format(label),
        )

# ================================================================================================
# 3. ONE SLIDE PER FAILING STUDY
# ================================================================================================
if not failing.empty:
    docs = list(dict.fromkeys(failing["document_uuid_s"]))
    for doc in docs:
        sdf = failing[failing["document_uuid_s"] == doc]
        r = meta_row(sdf)

        fig = one_study_figure(sdf, None)
        plot_html = fig.to_html(full_html=False, include_plotlyjs=False)

        meta_html = meta_table([
            ("FAILS", "<b style='color:#b00'>{}</b>".format(lib.esc(r.get("fails")))),
            ("material", lib.esc(r.get("publicname_s"))),
            ("owner / project", lib.esc(r.get("owner_name_s"))),
            ("source file", lib.esc(r.get("input_file"))),
            ("document uuid", "<span style='font-family:monospace;user-select:all'>{}</span>"
                               .format(lib.esc(r.get("document_uuid_s")))),
            ("links", links_html(r)),
        ])

        label = "{} | {}".format(r.get("publicname_s"), r.get("fails"))
        add_slide(
            "FAIL — {}".format(label),
            plot_html + meta_html,
            anchor_label="FAIL — {}".format(label),
        )

# ================================================================================================
# ASSEMBLE ONE HTML PAGE
# ================================================================================================
toc_html = "".join(
    "<li><a href='#{}'>{}</a></li>".format(anchor, lib.esc(text))
    for anchor, text in toc_entries
)
slide_sections[summary_slide_index] = slide_sections[summary_slide_index].replace(
    "{toc}", toc_html
)

page = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Genotox curation review — {project}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body {{ margin:0; background:{surface}; color:{ink}; font-family:Georgia,'Times New Roman',serif; }}
  h2 {{ font-family:Georgia,'Times New Roman',serif; color:{ink}; }}
  table {{ border-collapse:collapse; }}
  a {{ color:{accent}; }}
</style>
</head><body>
{sections}
</body></html>""".format(
    project=lib.esc(filter_project), sections="".join(slide_sections),
    surface=SURFACE, ink=INK, accent=CAT[0],
)

with open(product["data"], "w", encoding="utf-8") as f:
    f.write(page)

print("wrote", len(slide_sections), "slides to", product["data"])

# ================================================================================================
# DATA EXPORT — the actual dose-response data behind the slides, as an .xlsx workbook
# ================================================================================================
# Same long-format rows the slides are plotted from (no re-derivation), one sheet per split
# plus a de-duplicated per-study summary sheet for each — so a reviewer who wants the raw
# numbers (not just the plots) can filter/pivot them directly.

# Human-facing sheets lead with "material" (publicname_s), not a UUID — a domain expert reads
# by material name, not by document_uuid_s. UUID columns are kept ONLY on the raw dose-response
# sheets (for someone who needs to trace a row back to AMBIT), never on the overview/summary
# sheets a reviewer actually scans.
SUMMARY_COLS = [
    "publicname_s", "owner_name_s", "E.method_s", "E.cell_type_ss", "exposure_time",
    "reference_s", "reference_year_s", "input_file", "substance_url", "study_url",
    "document_uuid_s", "s_uuid_s",
]
PASSING_SUMMARY_EXTRA = ["assay", "c_conc3", "c_neg", "c_pos", "c_viab", "interpretable"]
FAILING_SUMMARY_EXTRA = ["fails"]


def excel_safe(df):
    """openpyxl can't write Python list objects into a cell (E.cell_type_ss was parsed to a
    list for HTML display) — join them back to a plain string for the spreadsheet."""
    df = df.copy()
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, list)).any():
            df[col] = df[col].apply(lambda v: ", ".join(map(str, v)) if isinstance(v, list) else v)
    return df


def per_study_summary(df, extra_cols):
    if df.empty:
        return df
    cols = [c for c in SUMMARY_COLS + extra_cols if c in df.columns]
    return excel_safe(df.drop_duplicates("document_uuid_s")[cols].reset_index(drop=True))


def autosize_and_freeze(ws):
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 60)


with pd.ExcelWriter(product["data_xlsx"], engine="openpyxl") as writer:
    sheets_written = 0

    if not overview_df.empty:
        overview_df.to_excel(writer, sheet_name="Materials overview", index=False)
        sheets_written += 1

    passing_summary = per_study_summary(passing, PASSING_SUMMARY_EXTRA)
    if not passing_summary.empty:
        passing_summary.to_excel(writer, sheet_name="Passing - summary", index=False)
        sheets_written += 1
    if not passing.empty:
        excel_safe(passing).to_excel(writer, sheet_name="Passing - dose-response", index=False)
        sheets_written += 1
    if not viability.empty:
        excel_safe(viability).to_excel(writer, sheet_name="Passing - viability", index=False)
        sheets_written += 1
    failing_summary = per_study_summary(failing, FAILING_SUMMARY_EXTRA)
    if not failing_summary.empty:
        failing_summary.to_excel(writer, sheet_name="Failing - summary", index=False)
        sheets_written += 1
    if not failing.empty:
        excel_safe(failing).to_excel(writer, sheet_name="Failing - dose-response", index=False)
        sheets_written += 1
    if sheets_written == 0:
        # openpyxl refuses to save a workbook with zero sheets — write an explanatory
        # placeholder rather than letting the task fail on a genuinely empty project.
        pd.DataFrame({"note": ["No passing or failing studies retrieved for this project."]}
                     ).to_excel(writer, sheet_name="No data", index=False)

    for ws in writer.book.worksheets:
        autosize_and_freeze(ws)

print("wrote", sheets_written or 1, "sheets to", product["data_xlsx"])

# ================================================================================================
# NEXUS EXPORT — same content as the CSV/Excel export, as a NeXus (.nxs) file
# ================================================================================================
# pyambit's to_nexus() writes its OWN model objects (Substances/SubstanceRecord/Study/
# ProtocolApplication/EffectRecord), not plain DataFrames. curate_passing.py/curate_failing.py
# already flattened the real AMBIT ProtocolApplication objects into long CSV rows and didn't
# keep the originals around, so rather than re-fetch from AMBIT here (a second network round
# trip for data already in hand), each passing/failing study's rows are rebuilt into a minimal
# — but valid — ProtocolApplication: one EffectRecord per dose-response point, grouped by
# document_uuid_s into studies, grouped by s_uuid_s into substances. Content matches the CSV/
# Excel export exactly (same rows, same fields); only the container format differs.
import pyambit.datamodel as ambit
from pyambit import nexus_writer  # noqa: F401  (registers .to_nexus() on the classes above)
import nexusformat.nexus.tree as nx


def row_to_effect_record(row, passed):
    conditions = {}
    if pd.notna(row.get("dose")):
        conditions["CONCENTRATION"] = ambit.Value(
            loValue=float(row["dose"]), unit=row.get("dose_unit") or None
        )
    if pd.notna(row.get("control_label")):
        conditions["TREATMENT"] = str(row["control_label"])
    conditions["interpretable"] = "yes" if passed else "no"
    if not passed and pd.notna(row.get("fails")):
        conditions["fails"] = str(row["fails"])

    result = ambit.EffectResult(
        loValue=float(row["response"]) if pd.notna(row.get("response")) else None,
        unit=row.get("response_unit") or None,
    )
    return ambit.EffectRecord(
        endpoint=str(row.get("endpoint") or "unknown"),
        conditions=conditions,
        result=result,
    )


def rows_to_protocol_application(sdf, passed):
    r = sdf.iloc[0]
    effects = [row_to_effect_record(row, passed) for _, row in sdf.iterrows()]
    owner = r.get("owner_name_s") or "unknown"
    citation_title = r.get("reference_s") or owner
    method = r.get("E.method_s")
    cell_type = r.get("E.cell_type_ss")
    parameters = {}
    if method:
        parameters["E.method"] = str(method)
    if cell_type:
        parameters["E.cell_type"] = (
            ", ".join(cell_type) if isinstance(cell_type, list) else str(cell_type)
        )
    if pd.notna(r.get("input_file")):
        parameters["__input_file"] = str(r["input_file"])
    return ambit.ProtocolApplication.create(
        protocol=ambit.Protocol(
            topcategory="TOX",
            category=ambit.EndpointCategory(
                code="PASSING" if passed else "FAILING",
                title="interpretable" if passed else "not interpretable",
            ),
        ),
        effects=effects,
        uuid=str(r["document_uuid_s"]),
        citation=ambit.Citation(title=str(citation_title), owner=str(owner),
                                year=int(r["reference_year_s"])
                                if pd.notna(r.get("reference_year_s")) else None),
        owner=ambit.SampleLink.create(str(r["s_uuid_s"]), str(owner)),
        parameters=parameters or None,
    )


def build_substances(passing_df, failing_df):
    frames = [(passing_df, True), (failing_df, False)]
    by_s_uuid = {}
    for df, passed in frames:
        if df.empty:
            continue
        for doc, sdf in df.groupby("document_uuid_s"):
            try:
                papp = rows_to_protocol_application(sdf, passed)
            except Exception as err:
                print("skipping", doc, "- could not build ProtocolApplication:", err)
                continue
            s_uuid = str(sdf.iloc[0]["s_uuid_s"])
            by_s_uuid.setdefault(s_uuid, {
                "name": sdf.iloc[0].get("publicname_s") or s_uuid, "study": [],
            })["study"].append(papp)

    substance_records = [
        ambit.SubstanceRecord(i5uuid=s_uuid, name=str(info["name"]),
                              publicname=str(info["name"]), study=info["study"])
        for s_uuid, info in by_s_uuid.items()
    ]
    return ambit.Substances(substance=substance_records)


substances = build_substances(passing, failing)
nxroot = nx.NXroot()
if substances.substance:
    substances.to_nexus(nxroot, hierarchy=True)
else:
    # Ploomber tracks data_nexus as a declared product and expects the file to exist after
    # the task runs — write an empty-but-valid root (mirrors the Excel "No data" sheet) rather
    # than skip the file entirely for a genuinely empty project.
    nxroot.attrs["note"] = "No passing or failing studies retrieved for this project."
nxroot.save(product["data_nexus"], mode="w")
print("wrote", len(substances.substance), "substances to", product["data_nexus"])
