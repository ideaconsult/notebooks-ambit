# + tags=["parameters"]
upstream = None
solr_url = None
solr_user_env = "ENM_USER"
solr_pass_env = "ENM_PWD"
categories = ["ENM_0000068_SECTION", "TO_GENETIC_IN_VITRO_SECTION"]
benchmark_responses = [10.0, 20.0, 50.0]
log_window = [-1.0, 3.0]
direction = "decreasing"
max_substances = 0
product = None
# -

# Benchmark-dose (BMD) embeddings for every study in the requested endpoint categories.
#
# What this produces, per property (material x protocol x method x cell type x exposure
# time x units), is the CDF of the benchmark concentration with its uncertainty --
# BMDL / BMD / BMDU are the 5th / 50th / 95th percentiles of one object -- consolidated
# over the laboratories that measured it, plus that CDF flattened into a fixed-length
# vector in log10 concentration. Euclidean distance between two such vectors is an RMS
# displacement in decades, so the vectors are directly indexable.
#
# WHY THIS TASK FETCHES INSTEAD OF READING THE CURATION CSVs
# ---------------------------------------------------------
# curate_passing.py / curate_failing.py already fetch dose-response data, but they do two
# things at once: they FILTER (on viz_metadata's `interpretable` flag, on project, and on
# max_studies) and they FETCH. A BMD embedding wants the second without the first --
# there is no reason to restrict an index to curated records, and a study that fails the
# NR2/EFSA interpretability criteria still has a perfectly good benchmark dose.
#
# The CSVs they write are also lossy for this purpose: study_to_long_rows keeps only
# dose / response / units / control_label, dropping errorValue, errQualifier and
# NUMBER_OF_REPLICATES. Those are exactly what the BMD interval is computed from -- without
# them BMDL, BMD and BMDU collapse onto one value and the interval reads as perfect
# certainty. So this task goes to the same Solr inventory viz_metadata starts from and
# fetches ProtocolApplication objects itself, keeping the replicate structure intact.
#
# Output is Solr JSON (one document per property, following the field-suffix conventions
# pyambit's solr_writer uses) plus a flat CSV of the vectors for the clustering task.

import json
import os
import uuid

import numpy as np
import pandas as pd
from requests.auth import HTTPBasicAuth

import tasks.genotox_curation_lib as lib
from pyambit.bmd import BmdSpec, bmd_vector, consolidate_providers, series_from_substance
from pyambit.datamodel import SubstanceRecord

# Credentials are optional: several endpoints are public, and fetch_studies already
# falls back to an unauthenticated request when a project has no Gravitee key set.
# Missing env vars therefore mean "anonymous", not "fail".
_user = os.environ.get(solr_user_env) if solr_user_env else None
_pass = os.environ.get(solr_pass_env) if solr_pass_env else None
auth = HTTPBasicAuth(_user, _pass) if _user and _pass else None
print("solr auth:", "basic ({})".format(_user) if auth else "anonymous")

FL = (
    "document_uuid_s,s_uuid_s,publicname_s,owner_name_s,reference_owner_s,"
    "endpointcategory_s,E.method_s,E.cell_type_ss,topcategory_s"
)

spec = BmdSpec(
    benchmark_responses=tuple(float(r) for r in benchmark_responses),
    direction=direction,
    log_window=(float(log_window[0]), float(log_window[1])),
)

# --- 1. inventory: every study in the requested categories, unfiltered ------------------
query = "type_s:metadata_study AND endpointcategory_s:({})".format(
    " OR ".join(categories)
)
inventory = lib.fetch_docs(solr_url, auth, query, FL)
print("studies in inventory:", len(inventory))
if inventory.empty:
    raise SystemExit("no studies matched {} - check solr_url and categories".format(query))

print(inventory.groupby("endpointcategory_s").size().to_string())

substances = sorted(inventory["s_uuid_s"].dropna().unique())
if max_substances:
    substances = substances[: int(max_substances)]
print("\nsubstances to fetch:", len(substances))

# --- 2. fetch the real ProtocolApplication objects --------------------------------------
# A silently empty cohort is the failure mode to avoid, so every skip is counted and the
# reason reported rather than swallowed.
skips = {}
records = []
for i, s_uuid in enumerate(substances, 1):
    server = lib.substance2server(s_uuid)
    if not server:
        skips.setdefault("unknown server tag", []).append(s_uuid)
        continue
    studies = []
    for category in categories:
        papps, reason = lib.fetch_studies(server, s_uuid, category=category)
        if reason:
            skips.setdefault(reason, []).append(s_uuid)
            continue
        studies.extend(papps)
    if not studies:
        skips.setdefault("no studies returned", []).append(s_uuid)
        continue
    name = inventory.loc[inventory["s_uuid_s"] == s_uuid, "publicname_s"]
    records.append(
        SubstanceRecord(
            name=str(name.iloc[0]) if len(name) else s_uuid,
            i5uuid=s_uuid,
            study=studies,
        )
    )
    if i % 25 == 0:
        print("  fetched {}/{}".format(i, len(substances)))

print("\nsubstances with studies:", len(records))
if skips:
    print("skipped:")
    for reason, uuids in sorted(skips.items(), key=lambda kv: -len(kv[1])):
        print("  {:<28} {}".format(reason, len(uuids)))

# --- 3. group by property, consolidate laboratories, estimate ---------------------------
documents = []
rows = []
n_failed = 0
for record in records:
    try:
        grouped = series_from_substance(record)
    except Exception as err:  # a malformed record must not stop the run
        n_failed += 1
        print("  grouping failed for {}: {}".format(record.i5uuid, err))
        continue

    for key, by_provider in grouped.items():
        try:
            profile = consolidate_providers(by_provider, spec)
            vector = bmd_vector(profile, spec)
        except Exception as err:
            n_failed += 1
            print("  BMD failed for {}: {}".format(key, err))
            continue

        doc = {
            "id": "bmd_{}".format(uuid.uuid4().hex),
            "type_s": "bmd",
            "substance_s": key.substance,
            "s_uuid_s": record.i5uuid,
            "topcategory_s": key.topcategory,
            "endpointcategory_s": key.category,
            "E.method_s": key.method,
            "effectendpoint_s": key.endpoint,
            "effectendpoint_type_s": key.endpointtype,
            "exposure_time_h_d": key.hours,
            "concentration_unit_s": key.concentration_unit,
            "response_unit_s": key.response_unit,
            "parameters_ss": list(key.parameters),
            "reference_owner_ss": list(profile.providers),
            "n_providers_i": len(profile.providers),
            "benchmark_responses_ds": [float(r) for r in spec.benchmark_responses],
            "bmdl_ds": [float(v) for v in profile.bmdl],
            "bmd_ds": [float(v) for v in profile.bmd],
            "bmdu_ds": [float(v) for v in profile.bmdu],
            "determined_bs": [bool(v) for v in profile.determined],
            "censored_fraction_ds": [float(v) for v in profile.censored_fraction],
            "control_d": None if not np.isfinite(profile.control) else float(profile.control),
            "control_route_s": profile.control_route,
            "bmd_unit_s": "log10 {}".format(key.concentration_unit),
            "bmd_vector_ds": [float(v) for v in vector],
        }
        documents.append(doc)
        rows.append(
            {
                "id": doc["id"],
                "substance": key.substance,
                "s_uuid_s": record.i5uuid,
                "endpointcategory_s": key.category,
                "method": key.method,
                "endpoint": key.endpoint,
                "hours": key.hours,
                "concentration_unit": key.concentration_unit,
                "providers": "|".join(profile.providers),
                "n_providers": len(profile.providers),
                "n_determined": int(np.sum(profile.determined)),
                "control_route": profile.control_route,
                **{
                    "v{:04d}".format(i): float(v) for i, v in enumerate(vector)
                },
            }
        )

print("\nproperties with a BMD:", len(documents))
print("failed:", n_failed)

if documents:
    multi = sum(1 for d in documents if d["n_providers_i"] > 1)
    print("properties with >=2 providers:", multi)
    print("  (that number is the ceiling on any cross-laboratory result)")
    widths = np.array(
        [
            np.median(np.array(d["bmdu_ds"]) - np.array(d["bmdl_ds"]))
            for d in documents
        ]
    )
    print("median BMDU-BMDL: {:.3f} decades".format(float(np.median(widths))))
    degenerate = int(np.sum(widths <= 1e-9))
    print("degenerate (zero-width) intervals:", degenerate)
    if degenerate:
        print("  WARNING: a zero-width interval means the replicate structure was lost")

# --- 4. write ---------------------------------------------------------------------------
os.makedirs(os.path.dirname(str(product["data"])), exist_ok=True)
with open(product["data"], "w", encoding="utf-8") as out:
    out.write(json.dumps(documents, indent=2, ensure_ascii=False))
print("\nwrote", len(documents), "documents to", product["data"])

pd.DataFrame(rows).to_csv(product["data_csv"], index=False)
print("wrote", len(rows), "vectors to", product["data_csv"])
