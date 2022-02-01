# + tags=["parameters"]
upstream = ["retrieve_templates"]
solr_api_key = None
solr_api_url = None
folder_output = None
query=None
model_embedding = None
hnsw_distance = None
# -

import io 
from pynanomapper import aa
from pynanomapper import units
from pynanomapper import client_solr
import pandas as pd
import os,os.path
def retrieve_params(solr_api_url,solr_api_key,query="*:*"):
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)    
    r = client_solr.get(solr_api_url ,query={"q": query, "wt": "json", "rows" : 1000000 , "fq" : "type_s:params"},auth=auth_object)
    
    tmp = pd.DataFrame(r.json()["response"]["docs"])
    return tmp

def get_facets(solr_api_url,solr_api_key,q=query,fields=["document_uuid_s","guidance_s","effectendpoint_s"]):
    config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
    if auth_object!=None:
        auth_object.setKey(solr_api_key)    
    facets = client_solr.Facets()
    return  facets.summary(solr_api_url,auth_object, query=q,fields=fields)        

import torch
import hnswlib
class KG:
    def __init__(self,terms_file,ann_index,model):
        self.e_idx = hnswlib.Index(space=hnsw_distance,dim=768)
        self.e_idx.load_index(ann_index )
        self.terms = pd.read_csv(terms_file,sep="\t",encoding="utf-8")
        self.lookup = {}

    def link_entity(self,query):
        if query in self.lookup:
            return self.lookup[query]

        embeddings = model.encode(query, 
                        show_progress_bar=False,
                        normalize_embeddings=True)

        labels,distances =  self.e_idx.knn_query(embeddings, k=3)
        links = []
        for label, distance in zip(labels[0],distances[0]):
            links.append(self.terms.iloc[label]["Class ID"])
        self.lookup[query] = links
        return links




    def study2kg(self,df,params):
        df.drop(columns=['id','type_s','__input_file_s','_version_','Vial_s'],inplace=True)
        df.drop_duplicates(inplace=True)
        print(df.shape)

        study_kg=[]
        for index,row in df.iterrows():
            print(index)
            doc = row["document_uuid_s"]
            if row["E.method_s"] == "supplier":
                continue
            for col in df.columns:
                if "document_uuid_s" == col:
                    continue
                if col.endswith("_UNIT_s") or col.endswith("QUALIFIER_s"):
                    continue            
                if pd.isnull(row[col]) or row[col]=="N/A":
                    continue
                else:
                    param_title = params.loc[params["field"]==col]["title"].values[0]
                    if col in ["guidance_s","topcategory_s","endpointcategory_s","E.method_s","E.sop_reference_s"]:
                        pass
                    else:

                        param_title_e = self.link_entity(param_title) 

                        for e in param_title_e:   
                            study_kg.append((doc,"keyword",e))
                        #print("{}\t{}\t{}".format(doc,"keyword",param_title))
                        if type(row[col])==str:
                            if not row[col].isnumeric():
                        #print("{}\t{}\t{}".format(doc,param_title,row[col]))
                                value_e = self.link_entity(row[col]) 
                                for val in value_e:
                                    study_kg.append((doc,"keyword",val))
        tmp = pd.DataFrame(study_kg)   
        tmp.drop_duplicates(inplace=True)
        return tmp

        
from sentence_transformers import SentenceTransformer

params = pd.read_csv(os.path.join(folder_output,"params.txt"),sep="\t",encoding="utf-8")

df = retrieve_params(solr_api_url,solr_api_key,query="*:*")    
print(df.shape)
ann_index=os.path.join(folder_output,"terms","{}_{}_hnswlib.index".format(model_embedding,hnsw_distance))
use_cuda = torch.cuda.is_available()
if use_cuda:
    print('__CUDNN VERSION:', torch.backends.cudnn.version())
    print('__Number CUDA Devices:', torch.cuda.device_count())
    print('__CUDA Device Name:', torch.cuda.get_device_name(0))
    print('__CUDA Device Total Memory [GB]:', torch.cuda.get_device_properties(0).total_memory / 1e9)
    torch_device = "cuda:0"
else:
    torch_device = "cpu"

            #distilbert-base-nli-stsb-mean-tokens for symmetric search

model = SentenceTransformer(model_embedding, device=torch_device)
terms_file = os.path.join(folder_output,"terms","terms.txt")
kg = KG(terms_file,ann_index,model)

tmp = kg.study2kg(df,params)
tmp.drop_duplicates(inplace=True)

#get_facets(solr_api_url,solr_api_key,q=query,fields=["document_uuid_s","guidance_s","effectendpoint_s"])
tmp.to_csv(os.path.join(folder_output,"pykeen","study_kgraph.txt"),sep="\t",index=False,header=False)