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
# usable for the paper, and how good is it":
#   1. Dose-response dashboard — dropdown per study, genotox (left) + paired cell-viability
#      (right) side by side, since a passing study's viability partner IS the point of the
#      "paired viability" criterion — worth seeing, not just knowing it exists.
#   2. A rich per-study summary table (material, method, cells, time range, concentration
#      range, study owner, study year, reference, all readiness flags, document_uuid) — this
#      replaces generic bar charts (result-type / per-source counts), which added little over
#      just reading the table.
#   3. NM coverage table — which nanomaterials have >=1 interpretable study per assay family.
#   4. Contributing files table — which source files/datasets are citable.
#   5. Dose-range sanity table — even passing studies can have a narrow/suspicious dose range.

# Ploomber runs each task script with its source directory (tasks/) on PYTHONPATH, so the
# sibling module is importable directly — no sys.path/__file__ manipulation needed (and
# __file__ isn't reliably set under Ploomber's execution anyway).
import tasks.genotox_curation_lib as lib

import pandas as pd
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

# --- fetch + flatten (genotox) ----------------------------------------------------------------
EXTRA_COLS = ("assay", "studyResultType_s", "E.method_s", "E.cell_type_ss",
             "reference_s", "reference_year_s", "concentration_count_i",
             "has_positive_control_b", "has_negative_control_b",
             "c_conc3", "c_neg", "c_pos", "c_viab", "interpretable")


def _extra_meta(row):
    return {c: row.get(c) for c in EXTRA_COLS}


data, not_retrieved = lib.fetch_and_flatten(
    sel, passing_by_substance, label_by_doc, extra_meta_fn=_extra_meta,
)
print("dose-response points:", len(data), "across",
      0 if data.empty else data["document_uuid_s"].nunique(), "studies")
print("not retrieved:", len(not_retrieved))

# --- fetch the paired cell-viability studies too (same substances, viability category) -------
viability_data, viability_doc_by_genotox_doc, via_not_retrieved = pd.DataFrame(), {}, []
if not data.empty:
    viability_data, viability_doc_by_genotox_doc, via_not_retrieved = lib.fetch_paired_viability(
        sel, passing_by_substance
    )
    print("viability dose-response points:", len(viability_data), "across",
          0 if viability_data.empty else viability_data["document_uuid_s"].nunique(), "studies")

# --- dump the data behind the plot to CSV ---------------------------------------------------
data.to_csv(product["data_csv"], index=False)
if not viability_data.empty:
    viability_data.to_csv(str(product["data_csv"]).replace(".csv", "_viability.csv"), index=False)
print("wrote", len(data), "rows to", product["data_csv"])

# --- interactive dashboard: genotox (left) + paired viability (right), per-study dropdown ----
if not data.empty:
    group_by_doc = {
        doc: (data.loc[data["document_uuid_s"] == doc, "assay"].iloc[0] or "?",
              data.loc[data["document_uuid_s"] == doc, "owner_name_s"].iloc[0] or "?")
        for doc in data["document_uuid_s"].unique()
    }

    fig = lib.build_dual_dropdown_figure(
        data, viability_data, viability_doc_by_genotox_doc,
        dropdown_label_fn=lambda r: "[{} | {}] {}".format(
            r.get("assay") or "?", r["owner_name_s"], r["label"]),
        dropdown_sort_key_fn=lambda doc: (group_by_doc[doc], doc),
    )

    # --- rich per-study summary table: material, method, cells, time range, concentration
    # range, owner, year, reference, all flags, document_uuid ----------------------------
    dose_pts_only = data[data["control_label"].isna() & data["dose"].notna()]
    dose_range = (
        dose_pts_only.groupby("document_uuid_s")
        .agg(dose_min=("dose", "min"), dose_max=("dose", "max"),
             n_dose_points=("dose", "count"), dose_unit=("dose_unit", "first"))
    )
    # exposure time isn't part of the dose-response frame (that's the dose axis, not time) —
    # E.EXPOSURE_TIME comes through as a param on the study; pull min/max per study if present.
    time_col = "param_E.EXPOSURE_TIME_t" if "param_E.EXPOSURE_TIME_t" in sel.columns else None

    studies_sorted = sorted(data["document_uuid_s"].unique(), key=lambda d: (group_by_doc[d], d))
    summary_rows = []
    for doc in studies_sorted:
        r = data[data["document_uuid_s"] == doc].iloc[0]
        sel_row = sel.loc[sel["document_uuid_s"] == doc]
        sel_row = sel_row.iloc[0] if not sel_row.empty else None
        dr = dose_range.loc[doc] if doc in dose_range.index else None
        via_doc = viability_doc_by_genotox_doc.get(doc)
        flags = " ".join(
            f for f, ok in (
                ("conc3", r.get("c_conc3")), ("neg", r.get("c_neg")),
                ("pos", r.get("c_pos")), ("viab", r.get("c_viab")),
            ) if ok
        )
        summary_rows.append(
            "<tr>"
            "<td style='font-family:monospace;user-select:all'>{doc}</td>"
            "<td>{material}</td><td>{method}</td><td>{cells}</td>"
            "<td>{time}</td>"
            "<td>{conc_lo} - {conc_hi} {conc_unit} (n={n})</td>"
            "<td>{owner}</td><td>{year}</td><td>{ref}</td>"
            "<td>{flags}</td>"
            "<td>{via}</td>"
            "<td><a href='{sub}' target='_blank'>substance</a></td>"
            "<td><a href='{stu}' target='_blank'>raw JSON</a></td>"
            "</tr>".format(
                doc=lib.esc(r["document_uuid_s"]),
                material=lib.esc(r.get("publicname_s")),
                method=lib.esc(r.get("E.method_s")),
                cells=lib.esc(r.get("E.cell_type_ss")),
                time=lib.esc(sel_row.get(time_col)) if (sel_row is not None and time_col) else "",
                conc_lo=dr.dose_min if dr is not None else "",
                conc_hi=dr.dose_max if dr is not None else "",
                conc_unit=lib.esc(dr.dose_unit) if dr is not None else "",
                n=int(dr.n_dose_points) if dr is not None else 0,
                owner=lib.esc(r["owner_name_s"]),
                year=lib.esc(r.get("reference_year_s")),
                ref=lib.esc(r.get("reference_s")),
                flags=lib.esc(flags),
                via=lib.esc(via_doc) if via_doc else "(none found)",
                sub=lib.esc(r["substance_url"]), stu=lib.esc(r["study_url"]),
            )
        )
    summary_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Interpretable studies — full summary "
        "(document_uuid_s / paired viability uuid are selectable — click and copy)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>document_uuid_s</th><th>material</th><th>method</th><th>cells</th>"
        "<th>exposure time</th><th>concentration range</th>"
        "<th>study owner</th><th>year</th><th>reference</th><th>flags met</th>"
        "<th>paired viability document_uuid_s</th><th></th><th></th></tr>"
        + "".join(summary_rows) + "</table></div>"
    )

    # --- NM coverage — nanomaterials with >=1 interpretable study per assay family ---------
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

    # --- Contributing files table -----------------------------------------------------------
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

    # --- Dose-range sanity table (narrowest series first) -----------------------------------
    dose_range_sorted = dose_range.reset_index().merge(
        data.drop_duplicates("document_uuid_s")[["document_uuid_s", "label"]],
        on="document_uuid_s",
    ).sort_values("n_dose_points")
    dose_rows = "".join(
        "<tr><td style='font-family:monospace;user-select:all'>{doc}</td><td>{lbl}</td>"
        "<td>{lo}</td><td>{hi}</td><td>{n}</td><td>{unit}</td></tr>".format(
            doc=lib.esc(r.document_uuid_s), lbl=lib.esc(r.label),
            lo=r.dose_min, hi=r.dose_max, n=r.n_dose_points, unit=lib.esc(r.dose_unit),
        )
        for r in dose_range_sorted.itertuples()
    )
    dose_range_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Dose-range sanity check (narrowest series first — spot-check even 'good' studies)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>document_uuid_s</th><th>label</th><th>dose min</th><th>dose max</th>"
        "<th>n points</th><th>unit</th></tr>{rows}</table></div>"
    ).format(rows=dose_rows)

    # splice everything into the figure's HTML, right before </body>
    extra_html = nm_coverage_html + contributing_html + dose_range_html + summary_html
    html_text = fig.to_html(full_html=True, include_plotlyjs="cdn")
    html_text = html_text.replace("</body>", extra_html + "</body>")
    with open(product["data"], "w", encoding="utf-8") as f:
        f.write(html_text)
    fig.show()

    print("\nNM coverage (rows):", len(nm_assay))
    print(nm_assay.to_string())
    print("Unique contributing files:", len(contributing))
    print("\nNarrowest dose ranges (top 10):")
    print(dose_range_sorted.head(10)[["document_uuid_s", "n_dose_points", "dose_min", "dose_max"]]
         .to_string(index=False))
    print("\nGenotox studies with a paired viability study found:",
          sum(1 for v in viability_doc_by_genotox_doc.values() if v))
    print("Genotox studies with NO paired viability study found:",
          sum(1 for v in viability_doc_by_genotox_doc.values() if not v))
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
