# + tags=["parameters"]
upstream = ["viz_metadata"]
filter_tag = ""                # matches the s_uuid_s server tag (e.g. "NNRG" = NanoREG, public)
filter_project = ""            # matches owner_name_s
filter_s_uuid = ""             # matches s_uuid_s
filter_document_uuid = ""      # matches document_uuid_s
filter_investigation_uuid = ""  # matches investigation_uuid_s
max_studies = 50               # safety cap on how many failing studies to fetch/plot
product = None
# -

# Genotox curation — retrieve & plot the ACTUAL data for FAILING studies.
#
# viz_metadata.py flags which in-vitro COMET/Micronucleus studies FAIL the NR2/EFSA
# interpretability criteria (>=3 concentrations, neg control, pos control, paired viability)
# and exports one row per study (document_uuid_s) to a CSV. That CSV only carries summary
# metadata. To curate a failing study a human needs the REAL dose-response data — to tell a
# true data gap from a metadata/indexing artefact (e.g. concentration_count_i == 0 because the
# dose axis was not captured as a Solr condition, even though the study has a real dose series).
#
# This task: read the readiness CSV -> pick failing studies (ANY criterion failed) -> group by
# substance -> fetch each substance's in-vitro genotox studies ONCE from its source AMBIT server
# -> keep only the failing document_uuids -> plot the dose-response as an interactive Plotly
# dashboard (HTML).
#
# Shared AMBIT fetch/parse/plot machinery lives in genotox_curation_lib.py (also used by
# curate_passing.py, the companion dashboard for interpretable==True studies).
#
# Verified against live data:
#   - document_uuid_s == the AMBIT study "uuid"
#   - {server}/substance/{s_uuid}/study?media=application/json&top=TOX
#         &category=TO_GENETIC_IN_VITRO_SECTION  returns only the in-vitro genotox studies
#   - some servers are PROTECTED (NGTX/NanoGenotox, RGNE/RISKGONE return 403) -> skip + record.
#     nanoreg1 (NNRG) and data.enanomapper.net (ENM) are public.

# Ploomber runs each task script with its source directory (tasks/) on PYTHONPATH, so the
# sibling module is importable directly — no sys.path/__file__ manipulation needed (and
# __file__ isn't reliably set under Ploomber's execution anyway).
import tasks.genotox_curation_lib as lib
from pynanomapper import aa
import pandas as pd
import plotly.graph_objects as go

# Human-readable reason(s) a study failed each NR2/EFSA criterion, taken from the readiness
# flags viz_metadata already computed. Used to annotate every plot/CSV row so the curator
# sees WHY the study was flagged, not just the data.
CRITERION_FLAGS = {
    "c_conc3": "needs >=3 concentrations",
    "c_neg":   "missing negative control",
    "c_pos":   "missing positive control",
    "c_viab":  "no paired cell-viability",
}


def failure_reasons(row):
    """Which criteria this study fails, as a '; '-joined string (from the readiness flags)."""
    reasons = [msg for flag, msg in CRITERION_FLAGS.items()
               if flag in row and not bool(row[flag])]
    return "; ".join(reasons) if reasons else "(passes all — included by filter)"

# -- do we need auth
config, config_servers, config_security, auth_object, msg = aa.parseOpenAPI3()

# --- select failing studies -----------------------------------------------------------------
csv_path = upstream["viz_metadata"]["data"]
df = pd.read_csv(csv_path)
print("readiness rows:", len(df))

sel = df[~df["interpretable"].astype(bool)].copy()     # a study fails if ANY criterion failed
print("failing studies:", len(sel))

# optional filters, OR-combined. Server tag / project name are human-typed labels -> matched
# case-insensitively. UUIDs are exact-match (case matters / is never ambiguous there).
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

# group failing document_uuids by substance -> fetch each substance once
failing_by_substance = sel.groupby("s_uuid_s")["document_uuid_s"].apply(set).to_dict()
# map document_uuid -> a readable label for the plot — full UUID (needed to find the record
# on the AMBIT UI, truncating it is useless) + method + cell type so the curator can identify
# the study without having to open the links first. owner_name_s (project, e.g. NANoREG) and
# reference_owner_s (the actual study owner/lab from the citation) are DISTINCT fields — show
# both.
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
print("substances to fetch:", len(failing_by_substance))

# --- fetch + flatten ------------------------------------------------------------------------
data, not_retrieved = lib.fetch_and_flatten(
    sel, failing_by_substance, label_by_doc,
    extra_meta_fn=lambda row: {"fails": failure_reasons(row)},
)
print("dose-response points:", len(data), "across",
      0 if data.empty else data["document_uuid_s"].nunique(), "studies")
print("not retrieved:", len(not_retrieved))

# --- fetch paired cell-viability studies too (where available) — a study can fail the
# c_viab criterion under viz_metadata's strict matching yet still have SOME viability data
# for the substance worth showing the curator, e.g. to judge whether the strict match was
# too strict or whether viability data is genuinely absent.
viability_data, viability_doc_by_genotox_doc, via_not_retrieved = pd.DataFrame(), {}, []
if not data.empty:
    viability_data, viability_doc_by_genotox_doc, via_not_retrieved = lib.fetch_paired_viability(
        sel, failing_by_substance
    )
    print("viability dose-response points:", len(viability_data), "across",
          0 if viability_data.empty else viability_data["document_uuid_s"].nunique(), "studies")

# --- dump the data behind the plot to CSV ---------------------------------------------------
data.to_csv(product["data_csv"], index=False)
print("wrote", len(data), "rows to", product["data_csv"])

# --- interactive dashboard: genotox (left) + viability if available (right), per-study
# dropdown --------------------------------------------------------------------------------
# Not small-multiples (unreadable past a handful of studies) — every study's traces are drawn
# once, and a dropdown toggles which set of traces is visible. x = dose (log), y = response,
# one line per endpoint. Non-numeric dose values (e.g. "C-"/"C+") are CONTROL rows — shown as
# starred points at the low end of the dose axis rather than dropped.
if not data.empty:
    # Group studies by failing-criteria signature so the dropdown is scannable by "what's
    # missing" without needing a second, client-side-linked dropdown (plotly's static-HTML
    # updatemenus can't rebuild each other's button lists dynamically).
    fails_by_doc = {doc: data.loc[data["document_uuid_s"] == doc, "fails"].iloc[0]
                    for doc in data["document_uuid_s"].unique()}

    fig = lib.build_dual_dropdown_figure(
        data, viability_data, viability_doc_by_genotox_doc,
        dropdown_label_fn=lambda r: "[{}] {}".format(r["fails"], r["label"]),
        dropdown_sort_key_fn=lambda doc: (fails_by_doc[doc], doc),
    )

    # --- HTML table of every study: real DOM text, selectable/copyable, always visible -----
    studies_by_fail_group = sorted(data["document_uuid_s"].unique(),
                                   key=lambda d: (fails_by_doc[d], d))
    table_rows = []
    for doc in studies_by_fail_group:
        r = data[data["document_uuid_s"] == doc].iloc[0]
        via_doc = viability_doc_by_genotox_doc.get(doc)
        table_rows.append(
            "<tr>"
            "<td style='font-family:monospace;user-select:all'>{doc}</td>"
            "<td>{owner}</td><td>{pub}</td><td>{fails}</td>"
            "<td style='font-family:monospace;user-select:all'>{infile}</td>"
            "<td style='font-family:monospace;user-select:all'>{via}</td>"
            "<td><a href='{sub}' target='_blank'>substance</a></td>"
            "<td><a href='{stu}' target='_blank'>raw JSON</a></td>"
            "</tr>".format(
                doc=lib.esc(r["document_uuid_s"]), owner=lib.esc(r["owner_name_s"]),
                pub=lib.esc(r["publicname_s"]), fails=lib.esc(r["fails"]),
                infile=lib.esc(r.get("input_file")),
                via=lib.esc(via_doc) if via_doc else "(none found)",
                sub=lib.esc(r["substance_url"]), stu=lib.esc(r["study_url"]),
            )
        )
    table_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Failing studies (document_uuid_s / input file / paired viability uuid are "
        "selectable — click and copy)</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>document_uuid_s</th><th>owner_name_s</th><th>publicname_s</th>"
        "<th>fails</th><th>__input_file</th><th>paired viability document_uuid_s</th>"
        "<th></th><th></th></tr>"
        + "".join(table_rows) + "</table></div>"
    )

    # --- unique (project, input file) pairs needing attention — the actual curation punch
    # list: which source files/datasets to go fix, not just which studies failed.
    attention = (
        data.drop_duplicates("document_uuid_s")[["owner_name_s", "input_file"]]
        .dropna(subset=["input_file"])
        .drop_duplicates()
        .sort_values(["owner_name_s", "input_file"])
    )
    attention_rows = "".join(
        "<tr><td>{}</td><td style='font-family:monospace;user-select:all'>{}</td></tr>"
        .format(lib.esc(o), lib.esc(f))
        for o, f in attention.itertuples(index=False)
    )
    projects_needing_attention = sorted(data["owner_name_s"].dropna().unique().tolist())
    attention_html = (
        "<div style='font-family:sans-serif;margin:1em'>"
        "<h3>Projects needing attention</h3><p>{projects}</p>"
        "<h3>Unique source files needing attention ({n})</h3>"
        "<table border='1' cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th>owner_name_s</th><th>__input_file</th></tr>{rows}</table></div>"
    ).format(
        projects=lib.esc(", ".join(projects_needing_attention)),
        n=len(attention), rows=attention_rows,
    )

    # splice the table + attention summary into the figure's HTML, right before </body>
    html_text = fig.to_html(full_html=True, include_plotlyjs="cdn")
    html_text = html_text.replace("</body>", attention_html + table_html + "</body>")
    with open(product["data"], "w", encoding="utf-8") as f:
        f.write(html_text)
    fig.show()

    print("\nProjects needing attention:", projects_needing_attention)
    print("Unique input files needing attention:", len(attention))
    print(attention.to_string(index=False))
else:
    go.Figure().update_layout(
        title_text="No plottable failing studies for the current filter"
    ).write_html(product["data"])
    print("no data to plot")

# --- curation finding: studies that could not be retrieved ----------------------------------
if not_retrieved:
    nr = pd.DataFrame(not_retrieved)
    print("\nCOULD NOT RETRIEVE / no plottable data:")
    print(nr.groupby("reason").size().to_string())
    print(nr.to_string(index=False))
