# + tags=["parameters"]
upstream = None
solr_url = None
solr_user = None
solr_pass = None
product = None
# -

# Generic per-study metadata extraction for the eNanoMapper metadata Solr collection.
#
# One output row per study (``document_uuid_s`` = one protocol application), carrying the
# fields a user needs to *filter, explore, visualise and export* in spectrasearch /
# ramanchada-api — without prescribing a use case (genotoxicity is just one example).
#
# Which AMBIT condition is the dose/concentration axis and which carries the control
# designation is **not hardcoded**: it comes from the per-category study config shared with
# the jToxKit viewer (`pyambit.study_config`, generated from jtoxkit-react/src/config/*.js).
# Solr stores conditions as `_CONDITION_<name>_<suffix>` (e.g. `_CONDITION_concentration_d`,
# `_CONDITION_material_s`), so field names are derived from the config keys.

import json
import re
import uuid

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from pynanomapper import annotation
from pynanomapper.client_solr import post
from pyambit import study_config as sc

auth = HTTPBasicAuth(solr_user, solr_pass)

# Fields actually present in the index (via Luke). A `_CONDITION_*` field that the config
# names but the index doesn't carry (e.g. a unit variant, or a key with a space like
# "total dose") would otherwise raise a Solr syntax/undefined-field error and abort the whole
# facet — so every condition field name is intersected with this set before use.
_luke = requests.get(
    solr_url + "/admin/luke", params={"numTerms": 0, "wt": "json"}, auth=auth, timeout=120
).json()
INDEXED_FIELDS = set(_luke.get("fields", {}).keys())

# --- control-token classification ------------------------------------------------------
# `_CONDITION_material_s` is overloaded: it holds both control designations
# (control_positive / control_negative / control_interference / solvent_control / "Blank")
# and ordinary treatment material names (TiO2, PLGA-PEO, ...). Only the former are controls.
def classify_control(value):
    s = str(value).strip().lower()
    if "positive" in s and ("control" in s or s.startswith("control_")):
        return "positive"
    if "negative" in s and ("control" in s or s.startswith("control_")):
        return "negative"
    if "interference" in s:
        return "interference"
    if "solvent" in s or s == "vehicle":
        return "solvent"
    if s == "blank":
        return "blank"
    if s in ("control",):
        return "control"
    return None  # a treatment/material name, not a control


def cond_field(name, suffix):
    """Solr condition field for a config condition key, or None if not in the index.

    e.g. concentration -> _CONDITION_concentration_d (if present).
    """
    field = "_CONDITION_{}_{}".format(name, suffix)
    return field if field in INDEXED_FIELDS else None


def cond_field_any(name, *suffixes):
    """Try suffix variants in order, return the first indexed field name, or None.

    Needed because the index has both `_unit_s` and `_UNIT_s` casings.
    """
    for s in suffixes:
        f = "_CONDITION_{}_{}".format(name, s)
        if f in INDEXED_FIELDS:
            return f
    return None


def first_val(bucket, key):
    b = bucket.get(key, {}).get("buckets", [])
    return b[0]["val"] if b else None


def join_vals(bucket, key):
    return ", ".join(str(b["val"]) for b in bucket.get(key, {}).get("buckets", []))


# --- discover categories present -------------------------------------------------------
cats_resp = post(
    solr_url,
    query={
        "q": "type_s:study",
        "rows": 0,
        "wt": "json",
        "json.facet": json.dumps(
            {"cat": {"type": "terms", "field": "endpointcategory_s", "limit": 1000, "mincount": 1}}
        ),
    },
    auth=auth,
).json()
categories = [b["val"] for b in cats_resp["facets"]["cat"]["buckets"]]
print("categories:", len(categories), "studies total")

# --- fetch all params docs upfront (one pass, cursor pagination) -----------------------
# params docs are flat top-level documents in Solr (not nested child docs).
# All dynamic fields are prefixed with "p." in the output to distinguish them from
# the study-level fields.  Solr type suffixes (_s, _d, …) are stripped.
_PARAMS_SKIP = {"type_s", "document_uuid_s", "id", "topcategory_s",
                "endpointcategory_s", "_version_", "s_uuid_s", "assay_uuid_s",
                "investigation_uuid_s", "owner_name_s", "publicname_s", "name_s",
                "guidance_s", "E.method_s", "E.cell_type_s"}

def _all_params(solr_url, auth):
    """Cursor-paginate through all type_s:params docs; return {document_uuid_s: {p.key: val}}."""
    out = {}
    cursor = "*"
    page = 2000
    while True:
        resp = requests.post(
            solr_url + "/select",
            data={"q": "type_s:params", "rows": page, "wt": "json", "fl": "*",
                  "sort": "id asc", "cursorMark": cursor},
            auth=auth, timeout=120,
        ).json()
        docs = resp.get("response", {}).get("docs", [])
        for pdoc in docs:
            doc_uuid = pdoc.get("document_uuid_s")
            if not doc_uuid:
                continue
            # --- 1. LOVALUE/UPVALUE ranges → single human-readable _s field -------------
            range_parts = {}
            for k, v in pdoc.items():
                if v is None:
                    continue
                for suffix, slot in (("LOVALUE_d", "lo"), ("UPVALUE_d", "up")):
                    if k.endswith(suffix):
                        prefix = k[: -len(suffix)]
                        range_parts.setdefault(prefix, {})[slot] = v
            for prefix in range_parts:
                for suffix, slot in (("LOQUALIFIER_s", "loq"), ("UPQUALIFIER_s", "upq"),
                                     ("ERRQUALIFIER_s", "errq"), ("UNIT_s", "unit")):
                    val = pdoc.get(prefix + suffix)
                    if val is not None:
                        range_parts[prefix][slot] = val
            _skip_range = {p + s for p in range_parts for s in
                           ("LOVALUE_d", "UPVALUE_d", "LOQUALIFIER_s", "UPQUALIFIER_s",
                            "ERRQUALIFIER_s", "UNIT_s")}

            # --- 2. plain scalar _d with sibling _UNIT_s → "value unit" attr_ field ------
            # k[:-1] strips only "d", keeping the "_" separator: E.EXPOSURE_TIME_d → E.EXPOSURE_TIME_
            scalar_units = {}
            for k, v in pdoc.items():
                if v is None or not k.endswith("_d"):
                    continue
                stem = k[:-1]                          # e.g. "E.EXPOSURE_TIME_"
                unit_key = stem + "UNIT_s"
                if unit_key in pdoc and pdoc[unit_key] is not None and stem + "LOVALUE_d" not in pdoc:
                    scalar_units[k] = (v, pdoc[unit_key], unit_key)
            _skip_scalar = {k for k in scalar_units} | {u for _, _, u in scalar_units.values()}

            params = {}
            for k, v in pdoc.items():
                if k in _PARAMS_SKIP or k in _skip_range or k in _skip_scalar or v is None:
                    continue
                # strip Solr type suffix → attr_ field (analyzed text, no suffix)
                bare = re.sub(r"_(s|d|ss|ds|i|b)$", "", k)
                params["attr_" + bare] = v

            # range strings → attr_ field (analyzed text, no _s suffix)
            for prefix, p in range_parts.items():
                lo, up = p.get("lo"), p.get("up")
                loq, upq = p.get("loq", ""), p.get("upq", "")
                unit = p.get("unit", "")
                if lo is not None and up is not None and lo != up:
                    val_str = "{} - {}".format(lo, up)
                elif lo is not None:
                    val_str = "{} {}".format(loq, lo).strip()
                else:
                    val_str = "{} {}".format(upq, up).strip()
                if unit:
                    val_str = "{} {}".format(val_str, unit)
                # prefix already ends with "_", e.g. "E.MEDIUM.ph_" → attr_E.MEDIUM.ph
                params["attr_" + prefix.rstrip("_")] = val_str.strip()

            # scalar+unit strings → attr_ field
            for k, (val, unit, _) in scalar_units.items():
                stem = k[:-1]                          # e.g. "E.EXPOSURE_TIME_"
                params["attr_" + stem.rstrip("_")] = "{} {}".format(val, unit).strip()

            out[doc_uuid] = params
        next_cursor = resp.get("nextCursorMark", cursor)
        if next_cursor == cursor or not docs:
            break
        cursor = next_cursor
    return out

print("fetching params …")
params_by_study = _all_params(solr_url, auth)
print("params loaded for", len(params_by_study), "studies")


# --- per-category study facet ----------------------------------------------------------
rows = []
for category in categories:
    dose_fields = sc.dose_condition_fields(category) or ["concentration"]
    control = sc.control_field(category) or "material"

    sub = {
        "owner":          {"type": "terms", "field": "owner_name_s",        "limit": 1},
        "publicname":     {"type": "terms", "field": "publicname_s",         "limit": 1},
        "s_uuid":         {"type": "terms", "field": "s_uuid_s",             "limit": 1},
        "substanceType":  {"type": "terms", "field": "substanceType_s",      "limit": 1},
        "topcategory":    {"type": "terms", "field": "topcategory_s",        "limit": 1},
        "method":         {"type": "terms", "field": "E.method_s",           "limit": 5},
        "method_syn":     {"type": "terms", "field": "E.method_synonym_ss",  "limit": 20},
        "endpoint":       {"type": "terms", "field": "effectendpoint_s",     "limit": 8,
                           "facet": {"unit": {"type": "terms", "field": "unit_s", "limit": 3}}},
        "guidance":       {"type": "terms", "field": "guidance_s",           "limit": 3},
        "result_type":    {"type": "terms", "field": "studyResultType_s",    "limit": 1},
        "reference":      {"type": "terms", "field": "reference_s",          "limit": 1},
        "reference_year": {"type": "terms", "field": "reference_year_s",     "limit": 1},
        "reference_owner":{"type": "terms", "field": "reference_owner_s",    "limit": 1},
        "assay":          {"type": "terms", "field": "assay_uuid_s",         "limit": 1},
        # cell type and animal model are direct study-doc fields
        "cell_type":      {"type": "terms", "field": "E.cell_type_s",        "limit": 20},
        "animal_model":   {"type": "terms", "field": "E.animal_model_s",     "limit": 10},
    }
    # control designation — only if the field exists in the index
    control_solr = cond_field(control, "s")
    if control_solr:
        sub["controls"] = {"type": "terms", "field": control_solr, "limit": 50}

    # exposure time: collect actual values + units as arrays
    exp_solr = cond_field("exposure_time", "d")
    if exp_solr:
        sub["exp_values"] = {"type": "terms", "field": exp_solr, "limit": 50}
    exp_unit_solr = cond_field_any("exposure_time", "unit_s", "UNIT_s")
    if exp_unit_solr:
        sub["exp_units"] = {"type": "terms", "field": exp_unit_solr, "limit": 10}

    # dose/concentration: terms facet on each configured field that's actually indexed
    # → returns actual concentration values, not just a count
    dose_solr = []  # list of (config_name, solr_value_field, solr_unit_field_or_None)
    for dname in dose_fields:
        vf = cond_field(dname, "d")
        if vf:
            uf = cond_field_any(dname, "unit_s", "UNIT_s")
            safe = dname.replace(" ", "_")
            sub["conc_vals_{}".format(safe)] = {"type": "terms", "field": vf, "limit": 200}
            if uf:
                sub["conc_units_{}".format(safe)] = {"type": "terms", "field": uf, "limit": 10}
            dose_solr.append((safe, uf is not None))

    q = {
        "q": "type_s:study AND endpointcategory_s:{}".format(category),
        "rows": 0,
        "wt": "json",
        "json.facet": json.dumps(
            {"studies": {"type": "terms", "field": "document_uuid_s", "limit": -1, "mincount": 1, "facet": sub}}
        ),
    }
    resp = post(solr_url, query=q, auth=auth).json()
    buckets = resp.get("facets", {}).get("studies", {}).get("buckets", [])

    for bk in buckets:
        # control roles
        ctrl_roles = set()
        for cb in bk.get("controls", {}).get("buckets", []):
            role = classify_control(cb["val"])
            if role:
                ctrl_roles.add(role)

        # concentration/dose: merge all configured dose fields into one sorted value array
        all_conc_vals = []
        all_conc_units = set()
        for safe, has_units in dose_solr:
            all_conc_vals.extend(b["val"] for b in bk.get("conc_vals_{}".format(safe), {}).get("buckets", []))
            if has_units:
                all_conc_units.update(b["val"] for b in bk.get("conc_units_{}".format(safe), {}).get("buckets", []))
        conc_vals = sorted(set(all_conc_vals))

        # exposure time values + units
        exp_vals = sorted(b["val"] for b in bk.get("exp_values", {}).get("buckets", []))
        exp_units = [b["val"] for b in bk.get("exp_units", {}).get("buckets", [])]

        # cell types + animal models
        cell_types = [b["val"] for b in bk.get("cell_type", {}).get("buckets", [])]
        animal_models = [b["val"] for b in bk.get("animal_model", {}).get("buckets", [])]

        rows.append({
            "document_uuid_s":              bk["val"],
            "endpointcategory_s":           category,
            "topcategory_s":                first_val(bk, "topcategory"),
            "owner_name_s":                 first_val(bk, "owner"),
            "publicname_s":                 first_val(bk, "publicname"),
            "s_uuid_s":                     first_val(bk, "s_uuid"),
            "substanceType_s":              first_val(bk, "substanceType"),
            "E.method_s":                   join_vals(bk, "method"),
            "E.method_synonym_ss":          [b["val"] for b in bk.get("method_syn", {}).get("buckets", [])] or None,
            "E.cell_type_ss":               cell_types or None,
            "E.animal_model_ss":            animal_models or None,
            "effectendpoint_ss":            [
                                                "{} ({})".format(eb["val"], units)
                                                if (units := ", ".join(
                                                    u["val"] for u in eb.get("unit", {}).get("buckets", [])
                                                    if u["val"]
                                                )) else eb["val"]
                                                for eb in bk.get("endpoint", {}).get("buckets", [])
                                            ] or None,
            "guidance_s":                   join_vals(bk, "guidance"),
            "studyResultType_s":            first_val(bk, "result_type"),
            "reference_s":                  first_val(bk, "reference"),
            "reference_year_s":             first_val(bk, "reference_year"),
            "reference_owner_s":            first_val(bk, "reference_owner"),
            "assay_uuid_s":                 first_val(bk, "assay"),
            "number_of_points_d":           bk["count"],
            # concentration arrays (the actual dose series, not just the count)
            "concentration_values_ds":      conc_vals or None,
            "concentration_units_ss":       sorted(all_conc_units) or None,
            "concentration_count_i":        len(conc_vals),  # derived, kept for Solr range filters
            # exposure time arrays
            "exposure_time_values_ds":      exp_vals or None,
            "exposure_time_units_ss":       exp_units or None,
            # control flags
            "has_positive_control_b":       "positive" in ctrl_roles,
            "has_negative_control_b":       "negative" in ctrl_roles,
            "has_interference_control_b":   "interference" in ctrl_roles,
            "has_solvent_control_b":        "solvent" in ctrl_roles,
            "control_roles_ss":             sorted(ctrl_roles),
        })
        # flatten param_* fields directly into the row; also store original key names
        # in param_names_ss so users can facet on "which params does this study have"
        study_params = params_by_study.get(bk["val"])
        if study_params:
            rows[-1].update(study_params)
            rows[-1]["param_names_ss"] = [k[len("attr_"):] for k in study_params]

df = pd.DataFrame(rows)
print("studies extracted:", len(df))

# --- metadata-collection identity ------------------------------------------------------
df["type_s"] = "metadata_study"
df["id"] = ["ms_{}".format(uuid.uuid4().hex) for _ in range(len(df))]

df.dropna(axis=1, how="all", inplace=True)
df.head()

# Drop null / empty-list values per record so the JSON is compact and Solr-importable
# (Solr ignores missing fields; null/[] would create spurious indexed values).
def _clean(record):
    return {k: v for k, v in record.items()
            if v is not None and not (isinstance(v, float) and pd.isna(v)) and v != []}

records = [_clean(r) for r in df.to_dict(orient="records")]
with open(product["data"], "w", encoding="utf-8") as outfile:
    # ensure_ascii=False keeps Unicode as-is; replace \/ → / (stdlib escapes forward
    # slashes by default to guard against </script> in HTML, not needed here).
    outfile.write(json.dumps(records, indent=2, ensure_ascii=False).replace("\\/", "/"))
