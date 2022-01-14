# + tags=["parameters"]
upstream = ["retrieve_templates"]
solr_api_key = None
solr_api_url = None
folder_output = None
# -

import yaml
import measurement
from pynanomapper import aa
from pynanomapper import units
from pynanomapper import client_solr
import pandas as pd
import os, os.path
import json

import logging
from logging.config import fileConfig
#fileConfig('logging_config.ini')
global logger
logger = logging.getLogger()

config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 

print(auth_object)
if auth_object!=None:
    auth_object.setKey(solr_api_key)

facets = client_solr.Facets()
q="owner_name_s:GRACIOUS"
df = facets.summary(solr_api_url,auth_object, query=q,fields=["document_uuid_s","topcategory_s","endpointcategory_s","E.method_s"])    
df

docs_query = client_solr.StudyDocuments()
docs_query.settings['endpointfilter'] = None 
materialfilter=None
docs_query.settings['query_guidance'] = None
docs_query.settings['query_organism'] = None
docs_query.setStudyFilter({"topcategory_s" : "*", "endpointcategory_s" : "*"})
docs_query.settings['fields'] = "*"                    
query = docs_query.getQuery(textfilter=q,facets=None,fq=None, rows=10000, _params=True, _conditions=True, _composition=True );
print(query)
r = client_solr.post(solr_api_url,query=query,auth=auth_object)

results = None
if r.status_code==200:

    try:
        rows = docs_query.parse(r.json()['response']['docs'],process=None)
        results = pd.DataFrame(rows)
    except:
        print(r.text);
else:
    logger.info(r.status_code)

#results.head()

params = pd.DataFrame([col.replace("x.params.","") for col in results.columns if col.startswith("x.params.")],columns=["param"])
params.sort_values(by=['param'],inplace=True)
params.to_csv(os.path.join(folder_output,"params.txt"),sep="\t",index=False,encoding="utf-8")
#params

template=None
try:
    with open(os.path.join(folder_output,"templates","pchem.json"), 'r',encoding="utf-8") as file:
        template = json.load(file)

    #print(template)
except Exception as err:
    print(err)
