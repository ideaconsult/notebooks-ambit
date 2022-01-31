# + tags=["parameters"]
upstream = None
folder_output = None
solr_api_url = None
solr_api_key = None
annotation_folder = None
query=None
plot_dose_response=None
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
_query = "*:*" if query=="" else query.replace("owner_name_s","owner_name_hs")
dfm = facets.summary(solr_api_url,auth_object, query=_query,fields=["owner_name_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
projects = dfm["owner_name_hs"].unique()
dfm.to_csv(os.path.join(folder_output,"data","projects.csv"))

for project in projects:
    dfm = facets.summary(solr_api_url,auth_object, query="owner_name_hs:{}".format(project),fields=["owner_name_hs","substanceType_hs","s_uuid_hs","publicname_hs","name_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    

    if dfm.shape[0]>0:
        dfm.to_csv(os.path.join(folder_output,"data","materials_{}.csv".format(project)))  
        dfs = facets.summary(solr_api_url,auth_object, query="owner_name_s:{}".format(project),fields=["owner_name_s","document_uuid_s"],fq='type_s:study',log_query=log_query,log_result=beautify)    

        dfs.to_csv(os.path.join(folder_output,"data","study_{}.csv".format(project)))
        print("Project `{}` Materials {} Studies {} Data {}".format(project,dfm.shape[0],dfs.shape[0],dfs["Number of data points"].sum()))


## Endpoints

_query = "*:*" if query=="" else query
df = facets.summary(solr_api_url,auth_object, query=_query,fields=["topcategory_s","endpointcategory_s","E.method_s"],log_query=log_query,log_result=beautify) 
df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category',"E.method_s": 'method'},inplace=True)
df.to_csv(os.path.join(folder_output,"data","endpoints_all.csv"))
#qgrid.show_grid(df[["category","endpoint","Number of data points"]])
df[["category","endpoint","Number of data points"]].head()

_query = "*:*" if query=="" else query
facets = client_solr.Facets()
facets.set_annotation_folder(annotation_folder)
df = facets.summary(solr_api_url,auth_object, query=_query,fields=["topcategory_s","endpointcategory_s","owner_name_s","E.method_s","E.cell_type_s","reference_owner_s"],log_query=log_query,log_result=beautify)    
df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category',"E.method_s": 'method','reference_owner_s' : 'Data provider',"E.cell_type_s":"Cell type"},inplace=True)
(df[["project","category","endpoint","method","Cell type","Data provider","Number of data points"]]).head()

## Material types

for project in projects:
    dfm = facets.summary(solr_api_url,auth_object, query="owner_name_hs:{}".format(project),fields=["owner_name_hs","substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
    if dfm.shape[0]>0:
        dfm.to_csv("materialtypes_{}.csv".format(project))  
        print("Project `{}` Material types {}".format(project,dfm.shape[0]))
        #display(dfm)

### All material types
_query = "*:*" if query=="" else query.replace("owner_name_s","owner_name_hs")
dfm = facets.summary(solr_api_url,auth_object, query=_query,fields=["substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
dfm.to_csv(os.path.join(folder_output,"data","materialtypes_all.csv")) 
dfm.head()

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

#df = get_docs(query)
#df.to_csv(os.path.join(folder_output,"results.txt"),sep="\t")





def plot_dose_response(df,method, endpoint,units, concentration_unit,facet_row="time",facet_col="Cell", color="publicname_s",imgfile="output.png"):
    
    fig = px.scatter(df, y="loValue_d", x="_CONDITION_concentration_d",   color=color, error_y="err_d",
                    facet_row =facet_row,facet_col = facet_col,
                    log_x=False, width=1200, height=1200,
                    hover_name='effectendpoint_s', 
                    hover_data=["publicname_s", "endpointcategory_s", "E.method_s","effectendpoint_s",'_CONDITION_concentration_d','document_uuid_s'],
                    labels={
                    "_CONDITION_concentration_d": "Concentration ({})".format(concentration_unit),
                    "loValue_d": "{} {}".format(endpoint,units),
                    "publicname_s": "Material",
                    "reference_owner_s" : "Provider"
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
    fig.update_layout(title_text="{}: {} ({})".format(method,endpoint,units), title_x=0.5)
    fig.show()
    fig.write_image(imgfile)
          
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px

# we don't want to read everything in one go

def dose_response_overview(query):
    _query = "*:*" if query=="" else query
    facets = client_solr.Facets()
    facets.set_annotation_folder(annotation_folder)
    _tag_method = "E.method_s"
    _tag_endpoint= "effectendpoint_s"
    _tag_endpoint_type= "effectendpoint_type_s"
    _tag_conc_unit = '_CONDITION_concentration_UNIT_s'
    _tag_conc = '_CONDITION_concentration_d'
    _tag_time_unit = '_CONDITION_exposure_time_UNIT_s'
    _tag_time = '_CONDITION_exposure_time_d'
    df = facets.summary(solr_api_url,auth_object, query=_query,fields=[
            "topcategory_s","endpointcategory_s",_tag_method,_tag_endpoint,"effectendpoint_type_s",
            _tag_conc,_tag_conc_unit,
            _tag_time,_tag_time_unit
            ],log_query=log_query,log_result=beautify)    

    df.head()

    columns = ['id', 'name_s', 'publicname_s', 'owner_name_s', 'substanceType_s',
            's_uuid_s', 'type_s', 'document_uuid_s', 'investigation_uuid_s',
            'assay_uuid_s', 'topcategory_s', 'endpointcategory_s', 'guidance_s',
            'endpoint_s', 'effectendpoint_s', 'effectendpoint_type_s',
            'reference_owner_s', 'reference_year_s', 'reference_s', 'loValue_d',
            'unit_s','E.method_s', 'E.cell_type_s',
            _tag_conc_unit, _tag_conc,
            _tag_time_unit, _tag_time,
            '_CONDITION_replicate_s', '_CONDITION_material_s', '_version_', 'err_d',
            'errQualifier_s', 'guidance_synonym_ss', 'effectendpoint_synonym_ss',
                'E.method_synonym_ss']
            
    for index,row in df.iterrows():
        method = row[_tag_method]
        endpoint= row[_tag_endpoint]

        query = "{}:{} {}:{} {}:[* TO *] ".format(_tag_method,method,_tag_endpoint,endpoint,_tag_conc)
        _query = {'q': query, 'fq': 'type_s:study', 'wt': 'json',  'rows': 10000}
        r = client_solr.post(solr_api_url,query=_query,auth=auth_object)
        
        tmp = pd.DataFrame(r.json()['response']['docs'])
        tmp["time"] = ""
        if not _tag_conc in tmp.columns:
            continue
        time = ""

        
        if _tag_time in tmp.columns:
            tmp["time"] = tmp[_tag_time]
        if _tag_time_unit in tmp.columns:
            tmp["time"] = tmp["time"] + " " + row[_tag_time_unit]      

        r.close()
        cells = tmp["E.cell_type_s"].unique()
        for cell in cells:
            tmp_cell = tmp.loc[tmp["E.cell_type_s"]==cell]
            units = tmp_cell["unit_s"].unique()
            for unit in units:
                tmp_endpoint_unit = tmp.loc[tmp["unit_s"]==unit]
                conc_units = tmp_endpoint_unit[_tag_conc_unit].unique()
                for cu in conc_units:
                    tmp_endpoint_unit_cu = tmp_endpoint_unit.loc[tmp_endpoint_unit[_tag_conc_unit]==cu]
                    if not tmp_endpoint_unit_cu.empty:
                        print(method,endpoint,cell,unit,cu)
            #print(tmp.columns)
                        #display(tmp_endpoint_unit_cu[["publicname_s",_tag_conc,_tag_conc_unit,"time","reference_owner_s"]].head())
                        imgfile = os.path.join(folder_output,"data","{}_{}_{}_{}_{}.png").format(method,endpoint,unit.replace("/","_"),cell,cu.replace("/","_"))
                        plot_dose_response(tmp_endpoint_unit_cu,method, endpoint,unit, cu,facet_row="time",facet_col="publicname_s",color="reference_owner_s",imgfile=imgfile)                
        #break;

if plot_dose_response:
    dose_response_overview(query)

def tests():
    tmp = df.groupby(["E.method_s"]).size().reset_index(name='counts')
    #tmp
    fig = px.pie(tmp, values='counts', names='E.method_s', title='Methods')
    fig.show()
    fig.write_image(os.path.join(folder_output,"data","methods.png"))                


    tmp = df.groupby(["Cell"]).size().reset_index(name='counts')
    #tmp
    fig = px.pie(tmp, values='counts', names='Cell', title='Cells')
    fig.show()
    fig.write_image(os.path.join(folder_output,"data","cells.png"))

