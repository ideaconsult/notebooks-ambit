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
import pandas as pd
pd.set_option('display.max_columns', None)

def get_templates(folder_output):
    try:
        with open(os.path.join(folder_output,"templates","pchem.json"), 'r',encoding="utf-8") as file:
            template = json.load(file)

        return template;
    except Exception as err:
        return None


def get_facets(solr_api_url,auth_object,q="*:*"):
    facets = client_solr.Facets()
    return  facets.summary(solr_api_url,auth_object, query=q,fields=["document_uuid_s","topcategory_s","endpointcategory_s","E.method_s"])    


def get_documents_by_method(solr_api_url,auth_object,q="*:*"):
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
    return results



def prepare(solr_api_url,solr_api_key,folder_output):
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)
    
    q="owner_name_s:GRACIOUS"

    templates = get_templates(folder_output)
    results = get_documents_by_method(solr_api_url,auth_object,q)
    params = pd.DataFrame([col.replace("x.params.","") for col in results.columns if col.startswith("x.params.")],columns=["param"])
    params["lookup"] = params["param"].apply(lambda x: "PARAMS_"+x.upper().replace(" ","_"))
    params["type"] = params["param"].apply(lambda x: "number" if x.endswith("_d") else ("QUALIFIER" if x.endswith("QUALIFIER") else ("unit" if x.endswith("UNIT") else "STRING")))
    params.sort_values(by=['param'],inplace=True)
    params.to_csv(os.path.join(folder_output,"params.txt"),sep="\t",index=False,encoding="utf-8")

    return templates,results,params


templates,results,params= prepare(solr_api_url,solr_api_key,folder_output)

#param_strings = params.loc[params["type"]=="STRING"]
#param_strings

_tag_method="x.params.E.method"
_tag_endpoint = "value.endpoint"
methods = results[_tag_method].unique()
#methods=["DLS","BET","AUC"]
for method in methods:
    results4method = results.loc[results[_tag_method]==method]
    tmp = results4method.dropna(axis=1,how="all")
    #display(results4method)
    #results4method.to_csv("method.csv")
    #print(results4method.columns)
    #cols = ["uuid.document",_tag_method]
    cols = [_tag_endpoint,_tag_method]
    for p in filter(lambda e : e.startswith("x.params."),tmp.columns):
        #tbd this condition
        if p == _tag_method or p == "x.params.material state" or p == "x.params.Operator" or p=="x.params.Sample name" or p == "x.params.date of analysis" or p=="x.params.date of preparation" or p=="x.params.batch" or p=="x.params.E.sop_reference" or p=="x.params.Vial":
            continue
        key = p.replace("x.params.","PARAMS_").replace(".","_").replace(" ","_").upper()
        try:
            if key in templates["templates"][method]:
                #print(p,key)
                cols.append(p)
        except Exception as err:
            #print(err)
            pass
    print(cols)
    
    try:
        tmp = tmp[cols].drop_duplicates().fillna("")
        #display(tmp)
        tmp.to_csv(os.path.join(folder_output,"{}.csv".format(method)))
        
        for r in tmp.index:
            msg = ""
            for c in cols:
                if c==_tag_endpoint:
                    msg = tmp[c][r] + " obtained by "
                elif c == _tag_method:
                    msg= msg + tmp[c][r] + "  analysis "
                else:
                    if tmp[c][r]!="":
                        msg = msg + " ," + c.replace("x.params.","").replace("T.","").lower() + " " + tmp[c][r]     
            msg = msg + "."
            print(msg)


    except Exception as err:
        print(err)