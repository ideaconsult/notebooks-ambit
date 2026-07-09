"""Query the live `metaenm` Solr collection for endpoint/parameter/unit
names actually in use, to help judge what a new raw term should harmonize
to (or whether a similar term is already indexed under a different
spelling).

`metaenm` (HTTP Basic Auth; URL is deployment-specific -- see env.yaml's
metaenm_solr_url, no default baked into code) is a *derived* per-study
metadata index -- one document per `document_uuid_s` -- built by
notebooks-ambit/enanomapper/pipelines/metadata from the raw AMBIT Solr
export (see pipelines/metadata/METADATA_PIPELINE.md). It is a separate,
read-only concern from nanodata's import-time dictionaries
(dictionaries.py) and undefined-report backlog (undefined_reports.py):
those are *what the importer needs* to resolve a raw term; metaenm is
*what's already live* across every project, useful context for judging a
harmonization target (e.g. "is E.method already indexed as 'COMET' or
'COMET ASSAY'?").

This module only ever does read-only Solr `/select` queries -- it has no
write path, matching every other tool in this MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

# The searchable fields most relevant to endpoint/parameter/unit
# harmonization, confirmed real in pipelines/metadata/METADATA_PIPELINE.md
# and pipelines/metadata/tasks/study_metadata.py: E.method_s /
# E.method_synonym_ss (method names + synonyms), effectendpoint_ss,
# endpointcategory_s / topcategory_s (protocol categories),
# param_names_ss (which param_<NAME>_t fields exist on a doc).
#
# effectendpoint_ss is metaenm-specific, not the raw AMBIT/dictionaries.py
# endpoint dictionary shape: confirmed live, its values are composite
# "ENDPOINT (unit)" strings (e.g. "VIABILITY (percent)",
# "BODYWEIGHT_AUTOPSY (g)") -- metaenm merges the endpoint and its unit
# into one field for this metadata index, unlike endpoint.properties
# (bare endpoint name -> ontology PURL) or a plain AMBIT Solr export's
# `_hs`/`E._ss` fields. Don't propose a dictionaries.py entry straight
# from an effectendpoint_ss value without stripping the "(unit)" suffix.
HARMONIZATION_FIELDS = (
    "E.method_s",
    "E.method_synonym_ss",
    "effectendpoint_ss",
    "endpointcategory_s",
    "topcategory_s",
    "param_names_ss",
)


@dataclass
class FacetTerm:
    value: str
    count: int


@dataclass
class MetaenmSearchResult:
    field: str
    query: str
    terms: list[FacetTerm]
    error: str | None = None


def _post(
    solr_url: str, query: dict, auth: HTTPBasicAuth, timeout: float = 30.0
):
    return requests.post(
        f"{solr_url}/select", data=query, auth=auth, timeout=timeout
    )


def search_field_terms(
    solr_url: str,
    user: str,
    password: str,
    field: str,
    query: str,
    *,
    limit: int = 20,
) -> MetaenmSearchResult:
    """Facet one `field` for terms containing `query`, most-frequent first
    -- i.e. "what values does this field actually take across the live
    index, near this term."
    """
    auth = HTTPBasicAuth(user, password)
    # Wildcard matches on these `_s`/`_ss` fields are raw `string` type
    # (unanalyzed, case-sensitive -- confirmed live: `*COMET*` matches
    # 2263 docs, `*comet*` matches 0). Values are a mix of AMBIT's
    # uppercase codes (E.method_s: 'COMET') and genuinely mixed/lowercase
    # free text (effectendpoint_ss: 'VIABILITY (percent)', 'autopsy
    # analysis') -- there is no single casing to normalize to, so try the
    # query as given and uppercased, and merge/dedupe by value.
    variants = {query, query.upper()}
    try:
        # Solr terms facets don't substring-match; use a filter query with
        # a wildcard against the field itself plus a terms sub-facet
        # scoped to the matches, so the result is "which actual indexed
        # values contain `query`", not merely "does `query` exist
        # verbatim."
        fq = " OR ".join(f"{field}:*{v}*" for v in variants)
        resp = _post(
            solr_url,
            {
                "q": "type_s:metadata_study",
                "fq": fq,
                "rows": 0,
                "wt": "json",
                "json.facet": (
                    f'{{"terms":{{"type":"terms","field":"{field}",'
                    f'"limit":{limit},"mincount":1}}}}'
                ),
            },
            auth,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        return MetaenmSearchResult(
            field=field, query=query, terms=[], error=str(e)
        )

    buckets = data.get("facets", {}).get("terms", {}).get("buckets", [])
    terms = [FacetTerm(value=b["val"], count=b["count"]) for b in buckets]
    return MetaenmSearchResult(field=field, query=query, terms=terms)


def search_harmonization_terms(
    solr_url: str,
    user: str,
    password: str,
    query: str,
    *,
    fields: tuple[str, ...] = HARMONIZATION_FIELDS,
    limit: int = 20,
) -> list[MetaenmSearchResult]:
    """search_field_terms() across every field in `fields`."""
    return [
        search_field_terms(solr_url, user, password, f, query, limit=limit)
        for f in fields
    ]
