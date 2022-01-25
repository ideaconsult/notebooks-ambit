# + tags=["parameters"]
upstream = None
folder_output = None
solr_api_url = None
solr_api_key = None
annotation_folder = None
query=None
# -

from pynanomapper import client_solr,aa
import os, os.path

config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
if auth_object!=None:
    auth_object.setKey(solr_api_key) 

def log_query(q):
    #logger.debug(q)
    pass
def beautify(r):
    pass


# Database records

facets = client_solr.Facets()
facets.set_annotation_folder(annotation_folder)
dfm = facets.summary(solr_api_url,auth_object, query=query.replace("owner_name_s","owner_name_hs"),fields=["owner_name_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
projects = dfm["owner_name_hs"].unique()
dfm.to_excel(os.path.join(folder_output,"data","projects.xlsx"))

for project in projects:
    dfm = facets.summary(solr_api_url,auth_object, query="owner_name_hs:{}".format(project),fields=["owner_name_hs","substanceType_hs","s_uuid_hs","publicname_hs","name_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    

    if dfm.shape[0]>0:
        dfm.to_csv(os.path.join(folder_output,"data","materials_{}.csv".format(project)))  
        dfs = facets.summary(solr_api_url,auth_object, query="owner_name_s:{}".format(project),fields=["owner_name_s","document_uuid_s"],fq='type_s:study',log_query=log_query,log_result=beautify)    

        dfs.to_csv(os.path.join(folder_output,"data","study_{}.csv".format(project)))
        print("Project `{}` Materials {} Studies {} Data {}".format(project,dfm.shape[0],dfs.shape[0],dfs["Number of data points"].sum()))


## Endpoints


df = facets.summary(solr_api_url,auth_object, query=query,fields=["topcategory_s","endpointcategory_s","E.method_s"],log_query=log_query,log_result=beautify) 
df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category',"E.method_s": 'method'},inplace=True)
df.to_csv(os.path.join(folder_output,"data","endpoints_all.csv"))
#qgrid.show_grid(df[["category","endpoint","Number of data points"]])
df[["category","endpoint","Number of data points"]]

facets = client_solr.Facets()
facets.set_annotation_folder(annotation_folder)
df = facets.summary(solr_api_url,auth_object, query=query,fields=["topcategory_s","endpointcategory_s","owner_name_s","E.method_s","E.cell_type_s","reference_owner_s"],log_query=log_query,log_result=beautify)    
df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category',"E.method_s": 'method','reference_owner_s' : 'Data provider',"E.cell_type_s":"Cell type"},inplace=True)
(df[["project","category","endpoint","method","Cell type","Data provider","Number of data points"]])

## Material types

for project in projects:
    dfm = facets.summary(solr_api_url,auth_object, query="owner_name_hs:{}".format(project),fields=["owner_name_hs","substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
    if dfm.shape[0]>0:
        dfm.to_csv("materialtypes_{}.csv".format(project))  
        print("Project `{}` Material types {}".format(project,dfm.shape[0]))
        #display(dfm)

### All material types
dfm = facets.summary(solr_api_url,auth_object, query=query.replace("owner_name_s","owner_name_hs"),fields=["substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
dfm.to_csv(os.path.join(folder_output,"data","materialtypes_all.csv")) 
dfm    

import pandas as pd

print(query)
#for index,row in df[["project","category","endpoint","method","Cell type","Data provider","Number of data points"]].iterrows():

def get_docs(query):
    docs_query = client_solr.StudyDocuments()
    docs_query.settings['endpointfilter'] = None 
    materialfilter=None
    docs_query.settings['query_guidance'] = None
    docs_query.settings['query_organism'] = None
    #docs_query.setStudyFilter({"topcategory_s" : "*", "endpointcategory_s" : row["endpoint"], "E.method_s" : "({})".format(row["method"])})
    #docs_query.setStudyFilter("*")
    docs_query.settings['fields'] = "*"                    
    _query = docs_query.getQuery(textfilter=query,facets=None,fq=None, rows=10000, _params=True, _conditions=False, _composition=False );
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

df = get_docs(query)
df.to_csv(os.path.join(folder_output,"results.txt"),sep="\t")


_query = {'q': 'owner_name_s:PATROLS', 'fq': 'type_s:study', 'wt': 'json',  'rows': 10000}
r = client_solr.post(solr_api_url,query=_query,auth=auth_object)

import numpy as np
df = pd.DataFrame(r.json()['response']['docs'])
df["time"] = df["_CONDITION_exposure_time_d"].astype(str)+  df["_CONDITION_exposure_time_UNIT_s"]
#df.fillna("",inplace=True)
#df["time"] = df.apply(lambda x: '{:d} {}'.format(int(x["_CONDITION_exposure_time_d"]), x["_CONDITION_exposure_time_UNIT_s"]), axis = 1)
#df.head()
df.rename(columns={'E.cell_type_s' : 'Cell'},inplace=True)
df.loc[df['Cell'] == 'NCI-H441'] = "H441"

columns = ['id', 'name_s', 'publicname_s', 'owner_name_s', 'substanceType_s',
       's_uuid_s', 'type_s', 'document_uuid_s', 'investigation_uuid_s',
       'assay_uuid_s', 'topcategory_s', 'endpointcategory_s', 'guidance_s',
       'endpoint_s', 'effectendpoint_s', 'effectendpoint_type_s',
       'reference_owner_s', 'reference_year_s', 'reference_s', 'loValue_d',
       'unit_s','E.method_s', 'E.cell_type_s',
       '_CONDITION_concentration_UNIT_s', '_CONDITION_concentration_d',
       '_CONDITION_exposure_time_UNIT_s', '_CONDITION_exposure_time_d',
       '_CONDITION_replicate_s', '_CONDITION_material_s', '_version_', 'err_d',
       'errQualifier_s', 'guidance_synonym_ss', 'effectendpoint_synonym_ss',
        'E.method_synonym_ss']
methods=df['E.method_s'].unique()
methods

import matplotlib.pyplot as plt

import plotly.express as px
for method in methods:
    #fig = plt.figure()
    
    _tmp1 = df.loc[df["E.method_s"]==method]
    endpoints =_tmp1['endpoint_s'].unique()
    for endpoint in endpoints:
        _forendpoint = _tmp1["endpoint_s"]==endpoint
        _forendpointtype = _tmp1['effectendpoint_type_s']=='AVERAGE'
        _tmp2 = _tmp1.loc[_forendpoint & _forendpointtype]
        print(_tmp1.loc[_forendpoint]['effectendpoint_type_s'].unique())
        cus = _tmp2['_CONDITION_concentration_UNIT_s'].unique()
        for cu in cus:
            _forcu = _tmp2['_CONDITION_concentration_UNIT_s']==cu
            _tmp3 = _tmp2.loc[_forcu]
            _tmp3.fillna("",inplace=True)
            units = _tmp3['unit_s'].unique()
            try:

                fig = px.scatter(_tmp3, y="loValue_d", x="_CONDITION_concentration_d",   color="publicname_s", error_y="err_d",
                            facet_row = "time",facet_col = 'Cell',
                            log_x=False, width=1200, height=1200,
                            hover_name='endpoint_s', hover_data=["publicname_s", "endpointcategory_s", "E.method_s","endpoint_s",'_CONDITION_concentration_d','document_uuid_s'],
                            labels={
                            "_CONDITION_concentration_d": "Concentration ({})".format(cu),
                            "loValue_d": "{} {}".format(endpoint,units),
                            "publicname_s": "Material"
                 },
                )
                fig.update_layout(
                        autosize=True,
                       # width=900,
                       # height=500,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'                       
                                )
                fig.update_xaxes(showgrid=True, gridwidth=1,linecolor='black', gridcolor='LightGray')
                fig.update_yaxes(showgrid=True, gridwidth=1,linecolor='black', gridcolor='LightGray')                
                    #fig.update_traces(textposition='top center')
                #category = _tmp3['endpointcategory_s'].unique()
                fig.update_layout(title_text="{} ({})".format(method,endpoint), title_x=0.5)
                fig.show()
                fig.write_image(os.path.join(folder_output,"data","{}_{}.png").format(endpoint,method))
            except Exception as err:
                print(err,method,endpoint,_tmp3['effectendpoint_type_s'].unique(),_tmp3["time"].unique())
                #display(_tmp3[["E.method_s","endpoint_s","publicname_s","loValue_d","unit_s","_CONDITION_concentration_d","_CONDITION_concentration_UNIT_s","time"]].head())


import plotly.express as px
tmp = df.groupby(["E.method_s"]).size().reset_index(name='counts')
tmp
fig = px.pie(tmp, values='counts', names='E.method_s', title='Methods')
fig.show()
fig.write_image(os.path.join(folder_output,"data","methods.png"))                

import plotly.express as px
tmp = df.groupby(["Cell"]).size().reset_index(name='counts')
tmp
fig = px.pie(tmp, values='counts', names='Cell', title='Cells')
fig.show()
fig.write_image(os.path.join(folder_output,"data","cells.png"))