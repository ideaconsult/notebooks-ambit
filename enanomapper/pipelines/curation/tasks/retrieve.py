# + tags=["parameters"]
upstream = ["retrieve_templates"]
solr_api_key = None
solr_api_url = None
folder_output = None
query=None
# -


import yaml
import measurement
from pynanomapper import aa
from pynanomapper import units
from pynanomapper import client_solr
import pandas as pd
import os, os.path
import json
import re
import pprint

import logging
from logging.config import fileConfig
#fileConfig('logging_config.ini')
global logger
logger = logging.getLogger()
import pandas as pd
pd.set_option('display.max_columns', None)

class Templates:
    def __init__(self,folder,subfolder = "templates",file="pchem.json"):
        self.load(folder,subfolder,file)
        pass

    def add(self, x):
        self.data.append(x)

    def template_by_method(self,section,method):
        _method = method
        if not (_method in self.templates):
            if _method in self.keys:
                _method = self.keys[_method]

        if _method in self.templates:
            return self.templates[_method]

        _method = section
        if not (_method in self.templates):
            if _method in self.keys:
                _method = self.keys[_method]
        if _method in self.templates:
            return self.templates[_method]
        return None

    def load(self,folder,subfolder = "templates",file="pchem.json"):
        try:
            with open(os.path.join(folder,subfolder,file), 'r',encoding="utf-8") as file:
                template = json.load(file)

            self.templates =  template["templates"];
            self.keys= template["template_keys"]
        except Exception as err:
            return None

    def is_method_parameter(self,p):
        p = p.replace("x.params.","")
        lookup = ["E.method","material state","Operator","Sample name","date of analysis","date of preparation","batch","E.sop_reference","Vial","_Version_","Guidance","__input_file"]
        return not (p in lookup)

    def clean_pynanomapper_field(self,p):
        p = re.sub("_d$","",p)  #we want numeric fields as well
        p = re.sub("_s$","",p) 
        p = re.sub("_hs$","",p)
        p = re.sub("_ss$","",p)
        if re.search("_UNIT$",p) != None:
            return None
        if re.search("_UPQUALIFIER$",p) != None:
            return None  
        if re.search("_LOQUALIFIER$",p) != None:
            return None              
        if re.search("_LOVALUE$",p) != None:
            return None    
        if re.search("_UPVALUE$",p) != None:
            return None        
        p = re.sub("^T.","T_",p)
        p = re.sub("^E.","E_",p)
        p = p.replace("x.params.","").replace(" ","_")

        return p

    def field2title(self,p):

        p = re.sub("^T_","",p)
        p = re.sub("^E_","",p)
        p = p.replace("-"," ").trim().lower()

        return p        

    def add_field(self,key,p):   
        p = self.clean_pynanomapper_field(p)                                    
        if p is None:
            return

        id = "params_{}".format(p).upper()

        p = re.sub("^T.","",p)
        p = re.sub("^E.","",p)        
        title = p.replace("_"," ")
        if not key in self.templates:
            self.templates[key] = []
        field = {"field":id,"Sheet":key,"Column":-1,"Value":title,"Unit":""}
        self.templates[key].append(field);

    def save(self,folder_output,subfolder = "templates",file="pchem.json"):
        try:
            with open(os.path.join(folder_output,subfolder,file), 'w',encoding="utf-8") as outfile:
                tmp = {"templates" : self.templates,"template_keys" : self.keys}
                json.dump(tmp, outfile)
        except Exception as err:
            print(err)        

def get_facets(solr_api_url,solr_api_key,q="*:*",fields=["document_uuid_s","topcategory_s","endpointcategory_s","E.method_s"]):
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)    
    facets = client_solr.Facets()
    return  facets.summary(solr_api_url,auth_object, query=q,fields=fields)    


def get_documents_by_method(solr_api_url,auth_object,q="*:*",method="BET"):
    docs_query = client_solr.StudyDocuments()
    docs_query.settings['endpointfilter'] = None 
    materialfilter=None
    docs_query.settings['query_guidance'] = None
    docs_query.settings['query_organism'] = None
    docs_query.setStudyFilter({"topcategory_s" : "*", "endpointcategory_s" : "*", "E.method_s" : "({})".format(method)})
    docs_query.settings['fields'] = "*"                    
    query = docs_query.getQuery(textfilter=q,facets=None,fq=None, rows=10000, _params=True, _conditions=True, _composition=True );
    #print(query)
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



def prepare(solr_api_url,solr_api_key,folder_output,query="owner_name_s:GRACIOUS",method="BET"):
    print(query)
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)
    
    q=query

    
    results = get_documents_by_method(solr_api_url,auth_object,q,method)


    return results

def cleanup(val):
    return val.replace("_"," ").replace("."," ");

import io 
def retrieve_params(solr_api_url,solr_api_key):
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)    
    r = client_solr.get(solr_api_url ,query={"q": "*:*", "wt": "csv", "rows" : 0},auth=auth_object)
    
    params =pd.read_csv(io.StringIO(r.content.decode('utf-8')))
    tmp = pd.DataFrame(params.columns,columns=["field"])
    tmp["type"] = tmp["field"].apply(lambda x: "number" if x.endswith("_d") else ("QUALIFIER" if x.endswith("QUALIFIER") else ("unit" if x.endswith("UNIT") else "STRING")))
    tmp["field_clean"]=tmp["field"].apply(lambda col: re.sub("_s$","",re.sub("_d$","",re.sub("_UPQUALIFIER_s$","",re.sub("_LOVALUE_d$","",re.sub("_LOQUALIFIER_s$","",re.sub("_UPVALUE_d$","",re.sub("_UNIT_s$","",col))))))).replace(".","_"))
    tmp["title"]=tmp["field_clean"].apply(lambda col: re.sub("^T_","",re.sub("^Е_","",col)).replace("_"," ").strip())
    tmp.sort_values(by=['field_clean'],inplace=True)
    return tmp

templates = Templates(folder_output)


_tag_method="x.params.E.method"
_tag_endpoint = "value.endpoint"
_tag_unit = "value.unit"
_tag_section = "p.oht.section"
#this could be done with facets
#tmp = results[[_tag_section,_tag_method]].drop_duplicates()

sentences=[]
facets = get_facets(solr_api_url,solr_api_key,q=query,fields=["endpointcategory_s","E.method_s"])

for index,row in facets.iterrows():
    section = row["endpointcategory_s"]
    method = row["E.method_s"]
    
    results= prepare(solr_api_url,solr_api_key,folder_output,query=query,method=method)
    _template_key = templates.template_by_method(section,method);
    
    #results4method = results.loc[results[_tag_method]==method]
    #results4method = results
    #tmp = results4method.dropna(axis=1,how="all")
    tmp = results
    #display(results4method)
    #results4method.to_csv("method.csv")
    #print(results4method.columns)
    #cols = ["uuid.document",_tag_method]
    cols = [_tag_endpoint,_tag_unit,_tag_method]
    cols_extra = []
    

    for p in filter(lambda e : e.startswith("x.params."),tmp.columns):
        #tbd this condition
        if templates.is_method_parameter(p):
            key = templates.clean_pynanomapper_field(p);
            
            if key is None:
                continue
            else:
                key = "PARAMS_{}".format(key.upper())
            
            try:
                if _template_key is None:
                    templates.add_field(method,p);
                    #cols_extra.append(p)                 
                elif key in _template_key:
                    #print(p,key)
                    cols.append(p)
                else:
                    print("!!!Parameter not in template for \t",method,"\t",p,"\t",key)
                    cols_extra.append(key)                    
            except Exception as err:
                #print(err)
                pass
    #print(cols)
    if _template_key is None:
        print(">>> '{} {}' template not found!".format(section,method))   
        _template_key = templates.template_by_method(section,method); 
        #pprint.pprint(_template_key)
    else:
        print(">>> ",section,method)
        print(cols_extra)
    try:
        tmp = tmp[cols].drop_duplicates().fillna("")
        #display(tmp)
        tmp.to_csv(os.path.join(folder_output,"data","{}.csv".format(method)))
        

        for r in tmp.index:
            msg = ""
            for c in cols:
                if c==_tag_endpoint:
                    msg = cleanup(tmp[c][r]) + " " + tmp[_tag_unit][r] + " obtained by "
                elif c==_tag_unit:
                    continue
                elif c == _tag_method:
                    msg= msg +cleanup(tmp[c][r]) + "  analysis "
                else:
                    if tmp[c][r]!="":
                        col="PARAMS_"+templates.clean_pynanomapper_field(c).upper()
                        #print(c,col,_template_key[col]["Value"])
                        msg =  "{} ,{} {}".format(msg,_template_key[col]["Value"],tmp[c][r])
            msg = msg + "."
            sentences.append(msg)
    


    except Exception as err:
        print(method,err)

templates.save(folder_output,"templates","pchem_new.json")       
pd.DataFrame(sentences,columns=["sentence"]).to_csv(os.path.join(folder_output,"sentences.csv"),index=False,encoding="utf-8")     

params = retrieve_params(solr_api_url,solr_api_key)
params.to_csv(os.path.join(folder_output,"params.txt"),sep="\t",index=False,encoding="utf-8")