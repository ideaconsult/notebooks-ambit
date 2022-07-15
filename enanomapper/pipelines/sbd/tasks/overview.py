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

dfm = facets.summary(solr_api_url,auth_object, query=query,
fields=["owner_name_s","publicname_s","name_s","topcategory_s","endpointcategory_s","E.method_s","effectendpoint_s","unit_s"],fq='type_s:study')    
dfm.head()

df = get_docs(query)

df.rename(columns={"x.params.Cell culture. Serum": "x.params.Serum"},inplace=True)
df['x.conditions.E.exposure_time_d']= df['x.conditions.E.exposure_time_d'].astype(str)
df.columns

df.head()

tmp = df[["p.oht.module","p.oht.section","m.public.name","x.params.E.cell_type","x.params.E.method","value.endpoint","x.params.Serum","x.conditions.E.exposure_time_d","p.study_provider","value.range.lo","value.range.up"]]
tmp = tmp.fillna(value={'value.range.lo':0,"x.params.E.cell_type":"","x.conditions.E.exposure_time_d" : "", "x.params.E.method": "","x.params.Serum":"","value.endpoint":""})
tmp.head()

import plotly.express as px

toxpi = tmp.loc[tmp["value.endpoint"]=="TOXPI"]

fig = px.bar(toxpi, y="value.range.lo", x="m.public.name", color="x.params.E.method",
#x.conditions.E.exposure_time_d
                #barmode="group", 
                facet_row = "x.conditions.E.exposure_time_d",
                facet_col = "x.params.Serum",
                hover_name="x.conditions.E.exposure_time_d",
                labels={"value.range.lo" : "ToxPi", "x.conditions.E.exposure_time_d" : "Time", "x.params.Serum" : "Serum",
                    "x.params.E.method" : "Method", "m.public.name" : "material" },
                height=800, width=1200)
           
fig.show()


toxpi_group = toxpi.groupby(["m.public.name","x.params.Serum","x.conditions.E.exposure_time_d"]).agg(TOXPI=('value.range.lo', sum)).reset_index()

fig = px.bar(toxpi_group, y="TOXPI", x="m.public.name", color="x.conditions.E.exposure_time_d",
#x.conditions.E.exposure_time_d
                #barmode="group",
                facet_row= "x.params.Serum",
                labels={"value.range.lo" : "ToxPi", "x.conditions.E.exposure_time_d" : "Time", "x.params.Serum" : "Serum",
                    "x.params.E.method" : "Method", "m.public.name" : "material" },
                     barmode="group",
                      category_orders={"x.conditions.E.exposure_time_d": ["6.0", "24.0", "72.0"]},
                    height=600, width=1200)
fig.show()

pvt = pd.pivot_table(tmp,values="value.range.lo",index = ["m.public.name"], 
        columns = ["p.oht.module","p.oht.section","x.params.E.method","value.endpoint","x.conditions.E.exposure_time_d"],
        aggfunc=max
        ,dropna = True)
pvt.columns = [' '.join(col).strip() for col in pvt.columns.values]
pvt.head()

pvt = toxpi_group.pivot_table(index="m.public.name",columns=["x.params.Serum","x.conditions.E.exposure_time_d"],values="TOXPI")
pvt.columns = [' '.join(col).strip() for col in pvt.columns.values]
import numpy as np
pvt_size = tmp.loc[tmp["value.endpoint"]=="PARTICLE_SIZE"].pivot_table(index="m.public.name",columns=["value.endpoint"],values="value.range.lo",aggfunc=np.mean)
pvt_size.columns = [''.join(col).strip() for col in pvt_size.columns.values]
pvt = pvt.join(pvt_size, lsuffix='_caller', rsuffix='_other')

fig = px.scatter(pvt.reset_index(), x="with 6.0",y="without 6.0" ,color="PARTICLE_SIZE",
    labels={"PARTICLE_SIZE" : "Size, nm", "with 6.0" : "With serum, 6h", "without 6.0" : "Without serum, 6h" }, hover_name="m.public.name")
fig.show()

fig = px.scatter(pvt.reset_index(), x="with 24.0",y="without 24.0" ,color="PARTICLE_SIZE",
    labels={"PARTICLE_SIZE" : "Size, nm", "with 24.0" : "With serum, 24h","without 24.0" : "Without serum, 24h" }, hover_name="m.public.name")
fig.show()

fig = px.scatter(pvt.reset_index(), x="with 72.0",y="without 72.0" ,color="PARTICLE_SIZE",
        labels={"PARTICLE_SIZE" : "Size, nm", "with 72.0" : "With serum, 72h","without 72.0" : "Without serum, 72h" }, hover_name="m.public.name")
fig.show()