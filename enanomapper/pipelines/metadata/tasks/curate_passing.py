# + tags=["parameters"]
upstream = ["viz_metadata"]
filter_tag = ""                # matches the s_uuid_s server tag (e.g. "NNRG" = NanoREG, public)
filter_project = ""            # matches owner_name_s
filter_s_uuid = ""             # matches s_uuid_s
filter_document_uuid = ""      # matches document_uuid_s
filter_investigation_uuid = ""  # matches investigation_uuid_s
max_studies = 50               # safety cap on how many passing studies to fetch/plot
product = None
# -

# Genotox curation — retrieve & plot the ACTUAL data for PASSING (interpretable) studies.
#
# Companion to curate_failing.py: same fetch/parse/plot machinery (shared via
# genotox_curation_lib.py), but selects studies where viz_metadata.py's `interpretable` flag
# is TRUE — i.e. all four NR2/EFSA criteria are met (>=3 concentrations, neg control, pos
# control, paired viability). The question here isn't "what's wrong" but "what's actually
# usable for the paper, and how good is it" — different summary tables follow from that:
#   1. NM coverage — which nanomaterials have >=1 interpretable study per assay family
#   2. Result-type distribution — what outcomes (positive/negative/equivocal) the good data show
#   3. Per-source counts — which projects contributed usable data
#   4. Contributing files — which source files/datasets are citable
#   5. Dose-range sanity table — even passing studies can have a narrow/suspicious dose range;
#      this lets a curator spot-check without opening every plot

# Ploomber runs each task script with its source directory (tasks/) on PYTHONPATH, so the
# sibling module is importable directly — no sys.path/__file__ manipulation needed (and
# __file__ isn't reliably set under Ploomber's execution anyway).
import tasks.genotox_curation_lib as lib

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- select passing (interpretable) studies --------------------------------------------------
csv_path = upstream["viz_metadata"]["data"]
df = pd.read_csv(csv_path)
print("readiness rows:", len(df))

sel = df[df["interpretable"].astype(bool)].copy()      # all four NR2 criteria met
print("interpretable studies:", len(sel))

# optional filters, OR-combined (same semantics as curate_failing.py)
masks = []
if filter_tag:
    masks.append(sel["s_uuid_s"].str.split("-").str[0].str.upper() == filter_tag.upper())
if filter_project:
    masks.append(sel["owner_name_s"].str.casefold() == filter_project.casefold())
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

# group passing document_uuids by substance -> fetch each substance once
passing_by_substance = sel.groupby("s_uuid_s")["document_uuid_s"].apply(set).to_dict()
label_by_doc = {
    row["document_uuid_s"]: "{} / {} | {} | {} | {} | {}".format(
        row.get("owner_name_s", "") or "?",
        row.get("reference_owner_s", "") or "?",
        row.get("publicname_s", ""),
        row.get("E.method_s", ""), row.get("E.cell_type_ss", ""),
        row["document_uuid_s"],
    )
    for _, row in sel.iterrows()
}
print("substances to fetch:", len(passing_by_substance))

# --- fetch + flatten ------------------------------------------------------------------------
data, not_retrieved = lib.fetch_and_flatten(
    sel, passing_by_substance, label_by_doc,
    extra_meta_fn=lambda row: {
        "assay": row.get("assay"),
        "studyResultType_s": row.get("studyResultType_s"),
    },
)
print("dose-response points:", len(data), "across",
      0 if data.empty else data["document_uuid_s"].nunique(), "studies")
print("not retrieved:", len(not_retrieved))

# --- dump the data behind the plot to CSV ---------------------------------------------------
data.to_csv(product["data_csv"], index=False)
print("wrote", len(data), "rows to", product["data_csv"])

# --- interactive dashboard: ONE plot area, pick the study via a dropdown --------------------
if not data.empty:
    # Group/label the dropdown by assay + project — "why" isn't the organizing question for
    # passing studies, "which assay/project" is.
    group_by_doc = {
        doc: (data.loc[data["document_uuid_s"] == doc, "assay"].iloc[0] or "?",
              data.loc[data["document_uuid_s"] == doc, "owner_name_s"].iloc[0] or "?")
        for doc in data["document_uuid_s"].unique()
    }

    fig = lib.build_dropdown_figure(
        data,
        dropdown_label_fn=lambda r: "[{} | {}] {}".format(
            r.get("assay") or "?", r["owner_name_s"], r["label"]),
        dropdown_sort_key_fn=lambda doc: (group_by_doc[doc], doc),
    )

    # --- HTML table of every study: real DOM text, selectable/copyable, always visible -----
    studies_sorted = sorted(data["document_uuid_s"].unique(), key=lambda d: (group_by_doc[d], d))
    table_rows = []
    for doc in studies_sorted:
        r = data[data["document_uuid_s"] == doc].iloc[0]
        table_rows.append(
            "<tr>"
            "<td style='font-family:monospace;user-select:all'>{doc}</td>"
            "<td>{owner}</td><td>{pub}</td><td>{assay}</td><td>{result}</td>"
            "<td style='font-family:monospace;user-select:all'>{infile}</td>"
            "<td><a href='{sub}' target='_blank'>substance</a></td>"
            "<td><a href='{stu}' target='_blank'>raw JSON</a></td>"
            "</tr>".format(
                doc=lib.esc(r["document_uuid_s"]), owner=lib.esc(r["owner_name_s"]),
                pub=lib.esc(r["publicname_s"]), assay=lib.esc(r.get("assay")),
                result=lib.esc(r.get("studyResultType_s")),
                infile=lib.esc(r.get("input_file")),
                sub=lib.esc(r["substance_url"]), stu=lib.esc(r["study_url"]),
            )
        )
    table_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Interpretable studies (document_uuid_s / input file are selectable — click and copy)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>document_uuid_s</th><th>owner_name_s</th><th>publicname_s</th>"
        "<th>assay</th><th>result type</th><th>__input_file</th><th></th><th></th></tr>"
        + "".join(table_rows) + "</table></div>"
    )

    # --- 1. NM coverage — nanomaterials with >=1 interpretable study per assay family ------
    nm_col = data["publicname_s"].fillna(data["s_uuid_s"])
    nm_assay = (
        pd.DataFrame({"nm": nm_col, "assay": data["assay"],
                     "document_uuid_s": data["document_uuid_s"]})
        .dropna(subset=["assay"])
        .drop_duplicates(["nm", "assay", "document_uuid_s"])
        .groupby(["nm", "assay"])["document_uuid_s"].nunique()
        .unstack(fill_value=0)
        .sort_index()
    )
    nm_rows = "".join(
        "<tr><td style='font-family:monospace;user-select:all'>{}</td>{}</tr>".format(
            lib.esc(nm),
            "".join("<td>{}</td>".format(int(nm_assay.loc[nm, a])) for a in nm_assay.columns),
        )
        for nm in nm_assay.index
    )
    nm_coverage_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Nanomaterial coverage (# interpretable studies per assay)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>nanomaterial</th>{headers}</tr>{rows}</table></div>"
    ).format(
        headers="".join("<th>{}</th>".format(lib.esc(a)) for a in nm_assay.columns),
        rows=nm_rows,
    )

    # --- 2. Result-type distribution --------------------------------------------------------
    result_counts = (
        data.drop_duplicates("document_uuid_s")["studyResultType_s"]
        .fillna("(unspecified)").value_counts().reset_index()
    )
    result_counts.columns = ["studyResultType_s", "studies"]
    fig_result = px.bar(
        result_counts, x="studyResultType_s", y="studies",
        title="Result type distribution among interpretable studies",
    )

    # --- 3. Per-source counts ----------------------------------------------------------------
    by_owner = (
        data.drop_duplicates("document_uuid_s").groupby("owner_name_s")
        .size().reset_index(name="interpretable_studies")
        .sort_values("interpretable_studies", ascending=False)
    )
    fig_owner = px.bar(
        by_owner, x="owner_name_s", y="interpretable_studies",
        title="Interpretable studies contributed per project",
    )
    fig_owner.update_layout(xaxis_tickangle=-45)

    # --- 4. Contributing files table -----------------------------------------------------
    contributing = (
        data.drop_duplicates("document_uuid_s")[["owner_name_s", "input_file"]]
        .dropna(subset=["input_file"])
        .drop_duplicates()
        .sort_values(["owner_name_s", "input_file"])
    )
    contributing_rows = "".join(
        "<tr><td>{}</td><td style='font-family:monospace;user-select:all'>{}</td></tr>"
        .format(lib.esc(o), lib.esc(f))
        for o, f in contributing.itertuples(index=False)
    )
    contributing_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Source files contributing usable data ({n})</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>owner_name_s</th><th>__input_file</th></tr>{rows}</table></div>"
    ).format(n=len(contributing), rows=contributing_rows)

    # --- 5. Dose-range sanity table ----------------------------------------------------------
    dose_pts_only = data[data["control_label"].isna() & data["dose"].notna()]
    dose_range = (
        dose_pts_only.groupby("document_uuid_s")
        .agg(dose_min=("dose", "min"), dose_max=("dose", "max"),
             n_dose_points=("dose", "count"), dose_unit=("dose_unit", "first"))
        .reset_index()
        .merge(data.drop_duplicates("document_uuid_s")[["document_uuid_s", "label"]],
              on="document_uuid_s")
        .sort_values("n_dose_points")
    )
    dose_rows = "".join(
        "<tr><td style='font-family:monospace;user-select:all'>{doc}</td><td>{lbl}</td>"
        "<td>{lo}</td><td>{hi}</td><td>{n}</td><td>{unit}</td></tr>".format(
            doc=lib.esc(r.document_uuid_s), lbl=lib.esc(r.label),
            lo=r.dose_min, hi=r.dose_max, n=r.n_dose_points, unit=lib.esc(r.dose_unit),
        )
        for r in dose_range.itertuples()
    )
    dose_range_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Dose-range sanity check (narrowest series first — spot-check even 'good' studies)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>document_uuid_s</th><th>label</th><th>dose min</th><th>dose max</th>"
        "<th>n points</th><th>unit</th></tr>{rows}</table></div>"
    ).format(rows=dose_rows)

    # splice everything into the figure's HTML, right before </body>
    extra_html = (
        nm_coverage_html
        + fig_result.to_html(full_html=False, include_plotlyjs=False)
        + fig_owner.to_html(full_html=False, include_plotlyjs=False)
        + contributing_html
        + dose_range_html
        + table_html
    )
    html_text = fig.to_html(full_html=True, include_plotlyjs="cdn")
    html_text = html_text.replace("</body>", extra_html + "</body>")
    with open(product["data"], "w", encoding="utf-8") as f:
        f.write(html_text)
    fig.show()
    fig_result.show()
    fig_owner.show()

    print("\nNM coverage (rows):", len(nm_assay))
    print(nm_assay.to_string())
    print("\nProjects contributing:", by_owner["owner_name_s"].tolist())
    print("Unique contributing files:", len(contributing))
    print("\nNarrowest dose ranges (top 10):")
    print(dose_range.head(10)[["document_uuid_s", "n_dose_points", "dose_min", "dose_max"]]
         .to_string(index=False))
else:
    go.Figure().update_layout(
        title_text="No plottable interpretable studies for the current filter"
    ).write_html(product["data"])
    print("no data to plot")

# --- studies that could not be retrieved -----------------------------------------------------
if not_retrieved:
    nr = pd.DataFrame(not_retrieved)
    print("\nCOULD NOT RETRIEVE / no plottable data:")
    print(nr.groupby("reason").size().to_string())
    print(nr.to_string(index=False))
