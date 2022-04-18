# + tags=["parameters"]
upstream = None
solr_url = None
solr_user = None
solr_pass = None
product = None
# -

from pynanomapper import client_solr
from pynanomapper import annotation
from requests.auth import HTTPBasicAuth
import json
import zlib

facets = client_solr.Facets()
#facets.set_annotation_folder("../../annotation")

df = facets.summary(solr_url,HTTPBasicAuth(solr_user, solr_pass), query="type_s:study",
            fields=["owner_name_s","substanceType_s","publicname_s","name_s","topcategory_s","endpointcategory_s","E.method_s","E.method_synonym_ss","E.cell_type_s","effectendpoint_s","effectendpoint_synonym_ss","document_uuid_s","assay_uuid_s","investigation_uuid_s"])              
df.dropna(axis=1,how="all",inplace=True)
df["type_s"] = "metadata"
df.head()


with open(product["data"], 'w') as outfile:
    outfile.write(df.to_json(orient = 'records',indent=2))