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
dfm = facets.summary(solr_api_url,auth_object, query=query,fields=["owner_name_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
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


df = facets.summary(solr_api_url,auth_object, query=query,fields=["topcategory_s","endpointcategory_s"],log_query=log_query,log_result=beautify)    

df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category'},inplace=True)
df.to_csv(os.path.join(folder_output,"data","endpoints_all.csv"))
#qgrid.show_grid(df[["category","endpoint","Number of data points"]])
df[["category","endpoint","Number of data points"]]

facets = client_solr.Facets()
facets.set_annotation_folder(annotation_folder)
df = facets.summary(solr_api_url,auth_object, query=query,fields=["topcategory_s","endpointcategory_s","owner_name_s"],log_query=log_query,log_result=beautify)    
df.rename(columns={'owner_name_s':'project','endpointcategory_name' : 'endpoint', 'topcategory_s' : 'category'},inplace=True)
(df[["project","category","endpoint","Number of data points"]])

## Material types

for project in projects:
    dfm = facets.summary(solr_api_url,auth_object, query="owner_name_hs:{}".format(project),fields=["owner_name_hs","substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
    if dfm.shape[0]>0:
        dfm.to_csv("materialtypes_{}.csv".format(project))  
        print("Project `{}` Material types {}".format(project,dfm.shape[0]))
        #display(dfm)

### All material types
dfm = facets.summary(solr_api_url,auth_object, query=query,fields=["substanceType_hs"],fq='type_s:substance',log_query=log_query,log_result=beautify)    
dfm.to_csv(os.path.join(folder_output,"data","materialtypes_all.csv")) 
dfm    