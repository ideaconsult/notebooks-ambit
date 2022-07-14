# + tags=["parameters"]
upstream = None
solr_api_url = None
solr_api_key = None
folder_output = None
query = None
product = None
# -

from pynanomapper import client_solr,aa
import os, os.path

import pandas as pd 

def get_docs(query):
    docs_query = client_solr.StudyDocuments()
    docs_query.settings['endpointfilter'] = None 
    materialfilter=None
    docs_query.settings['query_guidance'] = None
    docs_query.settings['query_organism'] = None
    #docs_query.setStudyFilter({"topcategory_s" : "*", "endpointcategory_s" : row["endpoint"], "E.method_s" : "({})".format(row["method"])})
    #docs_query.setStudyFilter("*")
    docs_query.settings['fields'] = "*"                    
    _query = docs_query.getQuery(textfilter=query,facets=None,fq=None, rows=10000, _params=True, _conditions=True, _composition=False );
    print(_query)
    r = client_solr.post(solr_api_url,query=_query,auth=auth_object)
    results = None
    if r.status_code==200:

     
        rows = docs_query.parse(r.json()['response']['docs'],process=None)
        results = pd.DataFrame(rows)
        return results
        
    else:
        print(r.status_code)
    return None

config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
if auth_object!=None:
    auth_object.setKey(solr_api_key)  

facets = client_solr.Facets()
#facets.set_annotation_folder(annotation_folder)
#_query = "*:*" if query=="" else query.replace("owner_name_s","owner_name_hs")
#dfm = facets.summary(solr_api_url,auth_object, query=_query,fields=["owner_name_hs"],fq='type_s:substance')    
#dfm.head()

df = get_docs(query)

df.head()

tmp = df[["p.oht.module","p.oht.section","m.public.name","x.params.E.cell_type","x.params.E.method","x.conditions.E.exposure_time_d","p.study_provider","value.endpoint","value.range.lo","value.range.up","x.params.Cell culture. Serum"]]
tmp = tmp.fillna(value={'value.range.lo':0,"x.params.E.cell_type":"","x.conditions.E.exposure_time_d" : "", "x.params.E.method": "","x.params.Cell culture. Serum":""})
tmp.head()

pvt = pd.pivot_table(tmp,values="value.range.lo",index = ["m.public.name"], 
        columns = ["p.oht.module","p.oht.section","x.params.E.method","x.conditions.E.exposure_time_d","value.endpoint"],
        aggfunc=max
        ,dropna = True)
pvt

#capture the  progression , consider one value for all assays
#compare with and without serum . do pairwise similarity for F5.1