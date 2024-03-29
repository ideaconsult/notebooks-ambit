# + tags=["parameters"]
upstream = ["retrieve","blueprint"]
folder_output = None
blueprint = None
model_embedding = None
hnsw_distance = None
prefix=None
terms_file=None
ann_index = None
ann_param_hits = None
# -

import pandas as pd
import requests
import os,os.path
import numpy as np
import hnswlib
import traceback



class Vocabulary:
    
    def __init__(self,folder,subfolder = "terms"):
        self.folder = folder
        self.subfolder = subfolder

    def load_ontology(self,url="https://data.bioontology.org/ontologies/ENM/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb&download_format=csv",
                    onto_file='enm.csv.gz',usecols=None, synonyms_sep=None,synonyms_fields=["Synonyms"],definition_fields=["Definitions"]):
        
        onto_file = os.path.join(self.folder,self.subfolder,onto_file)
        if not os.path.isfile(onto_file):
            print(url)
            enmfile = requests.get(url)
            open(onto_file, 'wb').write(enmfile.content)
        else:
            print(onto_file)
            
        cols=["Class ID","Preferred Label","Parents"]
        cols.extend(definition_fields)   
        cols.extend(synonyms_fields)

        enm=pd.read_csv(onto_file,compression='gzip',usecols=cols,dtype={'Parents':'category','Class ID':'category'})[cols]
        #enm.fillna(value="",inplace=True)
        enm['tmp_def'] = ''
        for definition_field in definition_fields:                  
            enm[definition_field].fillna('', inplace =True)   
            enm['tmp_def'] = enm['tmp_def'] + ' ' + enm[definition_field]
        enm.drop(columns=definition_fields,inplace=True)
        enm['tmp_def'] = enm['tmp_def'].str.strip()
        
        enm['tmp_synonym'] = ''
        for synonyms_field in synonyms_fields:                  
            enm[synonyms_field].fillna('', inplace =True)  
            enm['tmp_synonym'] = enm['tmp_synonym'] + enm[synonyms_field] + "|"
        enm['tmp_synonym'] = enm['tmp_synonym'].str.rstrip('|')
        enm.drop(columns=synonyms_fields,inplace=True)
        
            
        enm['Preferred Label'].fillna('', inplace =True)
        
        if synonyms_sep is None:
            pass
        else:
            enm['tmp_synonym'] = enm['tmp_synonym'].str.replace("|",synonyms_sep)
        #enm['Text'] = enm['Preferred Label'] + " " + enm['Definitions'] + " " + enm['Synonyms']
        #enm['Text'] =  enm['Synonyms']
        #enm['Text'] = enm['Text'].str.lower()
        enm.rename(columns={"tmp_synonym":"Synonyms","tmp_def":"Definitions"},inplace=True)
        if usecols is None:
            return enm
        else:
            enm = enm[usecols]
        
        return enm

    def load_ontology_byname(self,onto_name="ENM",synonyms_fields=["Synonyms"],definition_fields=["Definitions"]):
        
        url="https://data.bioontology.org/ontologies/{}/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb&download_format=csv".format(onto_name)
        df = self.load_ontology(url,
            onto_file="{}.csv.gz".format(onto_name.lower()),synonyms_fields=synonyms_fields,definition_fields=definition_fields)
        df["ontology"]=onto_name
        return df
    
    def load(self,name="ENM"):
        print(name)
        if name=="ENM": 
            return self.load_ontology_enm()
        elif name=="EFO": 
            return self.load_ontology_efo()
        elif name=="CSEO": 
            return self.load_ontology_cseo()
        else:
            return self.load_ontology_byname(name)

    def load_ontology_enm(self):
        return self.load_ontology_byname(onto_name="ENM",synonyms_fields=["Synonyms","has_exact_synonym","FULL_SYN"],definition_fields=["Definitions","definition","http://www.w3.org/2000/01/rdf-schema#isDefinedBy","DEFINITION"])

    def load_ontology_efo(self):
        return self.load_ontology_byname(onto_name="EFO",synonyms_fields=["Synonyms"],definition_fields=["Definitions","definition"])

    def load_ontology_cseo(self):
        return self.load_ontology_byname(onto_name="CSEO",synonyms_field="http://scai.fraunhofer.de/CSEO#Synonym",definition_fields=["http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#DEFINITION"])

vocab = Vocabulary(folder=folder_output)
try:
    #ontology = ["CHMO","BAO","EDAM","NPO"]
    ontology = ["CHMO","ENM","BAO"]
    #ontology = ["EDAM","EFO","CHEBI","IOBC","ECSO","FIX","REX","CCONT","OBCS","IAO","EXO","ECTO","HHEAR","CHEAR","PHENX","OAE","PATO","NPO","HUPSON","CRISP",
#"SWEET","CHEMINF","MMO","CHMO","BAO","MS","CLO","UO","MESH","OBI","TXPO","BIOMODELS","EDAM","LOINC","SBO","ENM"]
    
    print(terms_file)
    if os.path.isfile(terms_file):
        terms = pd.read_csv(terms_file,sep="\t",encoding="utf-8")
        #print(terms)
    else:
        terms = None

        for onto in ontology:
            try:
                tmp = vocab.load(onto)
                tmp["training"] = tmp["Preferred Label"] + ". " +tmp["Definitions"]            
                if terms is None:
                    terms = tmp
                else:
                    terms = pd.concat([terms,tmp])
            except Exception as err:
                print(err)
            
        blueprint_file = os.path.join(folder_output,"terms","blueprint.csv")
        if os.path.isfile(blueprint_file):
            blueprint = pd.read_csv(blueprint_file,sep="\t",encoding="utf-8")
            if terms is None:
                terms = blueprint
            else:
                terms = pd.concat([terms,blueprint])

        pd.DataFrame(terms).to_csv(terms_file,sep="\t",encoding="utf-8",index=False)
except Exception as err:
    print(err)


def ann(embedding_tensor,distance="ip"):
    dim = np.shape(embedding_tensor)[1]
    num_elements = np.shape(embedding_tensor)[0]

    data = embedding_tensor
    ids = np.arange(num_elements)

    # Declaring index
    p = hnswlib.Index(space = distance, dim = dim) # possible options are l2, cosine or ip

    # Initializing index - the maximum number of elements should be known beforehand
    p.init_index(max_elements = num_elements, ef_construction = 200, M = 16)

    # Element insertion (can be called several times):
    p.add_items(data, ids)

    # Controlling the recall by setting ef:
    p.set_ef(50) # ef should always be > k

    ### Index parameters are exposed as class properties:
    print(f"Parameters passed to constructor:  space={p.space}, dim={p.dim}") 
    print(f"Index construction: M={p.M}, ef_construction={p.ef_construction}")
    print(f"Index size is {p.element_count} and index capacity is {p.max_elements}")
    print(f"Search speed/quality trade-off parameter: ef={p.ef}")
    return p
    

    
#for index,row in tmp.iterrows():
#    print(row["Definitions"])

import torch


use_cuda = torch.cuda.is_available()
if use_cuda:
    print('__CUDNN VERSION:', torch.backends.cudnn.version())
    print('__Number CUDA Devices:', torch.cuda.device_count())
    print('__CUDA Device Name:', torch.cuda.get_device_name(0))
    print('__CUDA Device Total Memory [GB]:', torch.cuda.get_device_properties(0).total_memory / 1e9)
    torch_device = "cuda:0"
else:
    torch_device = "cpu"
from sentence_transformers import SentenceTransformer
    #distilbert-base-nli-stsb-mean-tokens for symmetric search

model = SentenceTransformer(model_embedding, device=torch_device)

import json
if not os.path.isfile(ann_index):

    definitions = terms["training"].to_list()

    embeddings = model.encode(definitions, 
                            show_progress_bar=False,
                            normalize_embeddings=True)
    embeddings.shape

    p = ann(embeddings)

    p.save_index(ann_index)

e_idx = hnswlib.Index(space=hnsw_distance,dim=768)
e_idx.load_index(ann_index )

#query="transmission electron microscope TEM"
#embeddings = model.encode(query, 
#                show_progress_bar=True,
#                normalize_embeddings=True)

##labels,distances =  e_idx.knn_query(embeddings, k=20)
#for label, distance in zip(labels[0],distances[0]):
#    print(distance,tmp.iloc[label]["Class ID"],"\t",tmp.iloc[label]["Preferred Label"],"\t",tmp.iloc[label]["Definitions"])      

params = pd.read_csv(os.path.join(folder_output,"params.txt"),sep="\t",encoding="utf-8")
prms =params["title"].unique()
#tmp = []


with open(ann_param_hits, 'w',encoding='utf-8') as f:
    f.write("{}\t{}\t{}\t{}\t{}\t{}\n".format("query","rank","distance","id","label","definition"));
    for prm in prms:
        query = prm
        embeddings = model.encode(query, 
                        show_progress_bar=False,
                        normalize_embeddings=True)

        labels,distances =  e_idx.knn_query(embeddings, k=3)
        rank = 1
        for label, distance in zip(labels[0],distances[0]):
            if distance<0.3:
                f.write("{}\t{}\t{}\t{}\t{}\t{}\n".format(query,rank,distance,terms.iloc[label]["Class ID"],terms.iloc[label]["Preferred Label"],terms.iloc[label]["Definitions"]))
                rank=rank+1


import spacy
#spacy.prefer_gpu()
nlp = spacy.load("en_core_web_sm")

text=("elements can be determined semiquantitatively using X-ray fluorescence (XRF)")
doc = nlp(text)
for chunk in doc.noun_chunks:
    query = chunk.text
    embeddings = model.encode(query, 
                            show_progress_bar=False,
                            normalize_embeddings=True)
    labels,distances =  e_idx.knn_query(embeddings, k=3)     
    rank = 1
    for label, distance in zip(labels[0],distances[0]):
        print("{}\t{}\t{}\t{}\t{}\t{}\n".format(query,rank,distance,terms.iloc[label]["Class ID"],terms.iloc[label]["Preferred Label"],terms.iloc[label]["Definitions"]))
        rank=rank+1     