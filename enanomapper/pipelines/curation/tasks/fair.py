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
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import json

config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
if auth_object!=None:
    auth_object.setKey(solr_api_key) 
facets = client_solr.Facets()
facets.set_annotation_folder(annotation_folder)

# FAIR - Findable

## Data model 

import pandas as pd

import pandas as pd

docs_query = "{}  +publicname_s:({})".format(query,"NRCWE-006")
print(docs_query)

_query = {'q': docs_query, 'fq': 'type_s:study', 'wt': 'json',  'rows': 10000}
r = client_solr.post(solr_api_url,query=_query,auth=auth_object)
tmp = pd.DataFrame(r.json()['response']['docs'])
print(tmp.shape)
print(tmp.columns)
tmp.head()

print(tmp["owner_name_s"].unique())
doc_uuids=tmp["document_uuid_s"].unique()
print(tmp["E.method_s"].unique())
#for doc_uuid in doc_uuids:
#    doc = tmp.loc[tmp["document_uuid_s"]==doc_uuid]
cols = ["publicname_s","document_uuid_s","effectendpoint_s","loValue_d","E.method_s","unit_s"]
fig = px.treemap(tmp[cols],path =["publicname_s",'E.method_s',"document_uuid_s","effectendpoint_s"],
                  values = 'loValue_d',color  = 'effectendpoint_s' )                 
   # fig3 = px.sunburst(doc[cols],path =["publicname_s",'E.method_s',"document_uuid_s","effectendpoint_s"],
                #    values = 'loValue_d',color  = 'effectendpoint_s')
fig.show()


from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.database import RDS
from diagrams.aws.network import ELB
from diagrams.generic.blank import Blank
from diagrams.programming.flowchart import Document,Preparation,InputOutput,InternalStorage,MultipleDocuments,PredefinedProcess,Merge,Database
from diagrams.generic.storage import Storage
from diagrams.custom import Custom


def draw_data_model(df , material_uuid):
    mdf = df.loc[df["s_uuid_s"]==material_uuid]
    with Diagram("Data model", filename=material_uuid,outformat="png", show=False):
        material = Custom(material_uuid, "../resources/graphene.png")

        with Cluster("Material metadata"):
            for name in ["publicname_s","name_s","substanceType_s"]:
                publicname = mdf[name].unique()
                publicname_node = Custom(publicname[0], "../resources/code.png")
                publicname_node >> Edge(color="blue", style="dashed",label=name.replace("_s","")) >> material
            publicname_node = Custom("Other identifiers", "../resources/code.png")
            publicname_node >> Edge(color="blue", style="dashed",label="identifier") >> material

        with Cluster("Material composition"):
            publicname_node = Custom("Component", "../resources/particle.png")
            publicname_node >> Edge(color="gray", style="dashed",label="role") >> material            

        iuids = mdf["investigation_uuid_s"].unique() 
        for iuid in iuids:	
            idf = mdf.loc[df["investigation_uuid_s"]==iuid]
            #with Cluster("Investigation {}".format(iuid)):
            try:
                docuuids = idf["document_uuid_s"].unique()    
                for docuuid in docuuids:
                    ddf = idf.loc[df["document_uuid_s"]==docuuid]    
                    
                    owner = ddf["reference_owner_s"].unique() 
                    owner_node = Custom(owner[0], "../resources/university.png")
                    reference = ddf["reference_s"].unique() 
                    ref_node = Custom(reference[0], "../resources/scroll.png")
                    

                    methods = ddf["E.method_s"].unique() 
                    

                    cell = ddf["E.cell_type_s"].unique() 
                    
                    with Cluster(docuuid):
                        papp = Custom("{}".format(docuuid), "../resources/microscope.png")
                        cellnode = Custom(cell[0], "../resources/tissues.png")
                        method = Custom("{}".format(methods[0].replace("_"," ")), "../resources/exam.png")
                        cellnode >> Edge(color="firebrick", style="dashed",label="cell") >> method
                        method_params = [method]

                    papp >> Edge(color="firebrick", style="dashed",label="reference") >> ref_node
                    method_params >> Edge(color="firebrick", style="dashed",label="method") >> papp

                    owner_node >> Edge(color="darkgreen", style="dashed",label="study provider") >> method_params

                    endpoints = ddf["effectendpoint_s"].unique() 
                    
                    i = 1
                    for endpoint in endpoints:
                        with Cluster("measurement {}".format(docuuid)):
                            edf = ddf.loc[df["effectendpoint_s"]==endpoint]
                            ep = Custom(endpoint.replace("_"," "),"../resources/metrics.png") 
                            time = Custom("Time, dose","../resources/capsule.png")
                            ep >> Edge(color="firebrick", style="dashed",label="conditions") >> time
                            papp >> Edge(color="black", style="dashed",label="endpoint") >> ep    
                            val_node = Custom("values", "../resources/line-chart.png")
                            time >> Edge(color="firebrick", style="dashed",label="values") >> val_node
                            
                        i=i+1
                    material >> Edge(color="black", style="bold") >> papp
            except:
                pass                        

        


substance_uuids=tmp["s_uuid_s"].unique()
#print(substance_uuids)
for substance_uuid in substance_uuids:
    print(substance_uuid)
    draw_data_model(tmp,substance_uuid)
    #break



## F1 Unique identifiers

### Material identifiers

_query = "*:*" if query=="" else query.replace("owner_name_s","owner_name_hs")
dfm = facets.summary(solr_api_url,auth_object, query=_query,fields=["name_hs","publicname_hs","substanceType_hs","owner_name_hs"],fq='type_s:substance')    
#projects = dfm["owner_name_hs"].unique()
dfm.head()

dfm.to_csv(os.path.join(folder_output,"data","materials.csv"),index=False)
json11ty = []
materials = dfm.drop(columns=["owner_name_hs"])
materials.drop_duplicates(inplace=True)
for index,row in materials.iterrows():
    tmp = {
			"ERM": row["publicname_hs"],
			"id": row["publicname_hs"],
			"name": row["name_hs"],
			"casrn": "",
			"type": row["substanceType_hs"],
			"supplier": "",
			"supplier_code": "",
			"batch": "",
			"core": "",
			"material_state" : "",
			"presense_of_dispersant" : "",
			"dispersant_reference" : ""				
		}
    json11ty.append(tmp)
with open(os.path.join(folder_output,"data","materials.json"), 'w',encoding="utf8") as outfile:
    json.dump(json11ty, outfile)         

tmp = dfm.groupby(["substanceType_name"]).size().reset_index(name='counts')
    #tmp
tmp.head()

fig = px.pie(tmp, values='counts', names='substanceType_name', title='Materials')
fig.show()
#fig.write_image(os.path.join(folder_output,"data","materials.png"))


### Assay, Investigation, Document , provider , reference (DOI)

#separate query for synonyms
_query = "*:*" if query=="" else query
print(_query)
dfstudy = facets.summary(solr_api_url,auth_object, query=_query,
    fields=["owner_name_s","investigation_uuid_s","topcategory_s","endpointcategory_s",
                "E.method_s","effectendpoint_s","E.cell_type_s"
        ],fq='type_s:study')    
#projects = dfm["owner_name_hs"].unique()
dfstudy.head()

dfstudy.to_csv(os.path.join(folder_output,"data","study.csv"),index=False)



## F2 Rich metadata

### High level metadata (Dataset name, description, source, rights holder, rights, e.g)
### Domain specific - list parameters  per assay  
### Schema.org ; Google dataset

## F3 Metadata/data linkage Metadata clearly and explicitly include the identifier of the data they describe

# FAIR - Accessible 

## A1 Standard communication protocol (Meta)data are retrievable by their identifier using a standardised communications protocol 

### A1.1 Open communication protocol

### A1.2 Privacy

## A2 Metadata even without data

# FAIR - Interoperable 

## I1 Representation

## I2 Vocabularies

## I3 Metadata links

# FAIR - Reusable

## R1 Rich metadata 
#Meta(data) are richly described with a plurality of accurate and relevant attributes.

### R1.1 License

### R1.2 Provenance

### R1.3 Domain standards compliance