# + tags=["parameters"]
upstream = ["spacy","retrieve_study_metadata"]
folder_output = None
model_embedding = None
hnsw_distance = None
ann_pdf_hits = None
prefix = None
study_kgraph_file = None
# -

#idea - terms should be properties in the graph

import os
import pandas as pd
import json

df = pd.read_csv(ann_pdf_hits,sep="\t")

training_file = os.path.join(folder_output,"pykeen","{}{}_{}_pdf_training.txt".format(prefix,model_embedding,hnsw_distance))
kg_file = os.path.join(folder_output,"pykeen","{}results".format(prefix))


training = df[["file","rank","id"]]
training = training.loc[training["rank"]==1]
training["rank"] = "keyword"
training.to_csv(training_file,sep="\t",index=False,header=False)

import shutil

combinedtraining_file = os.path.join(folder_output,"pykeen","{}{}_{}_pdf_combinedtraining.txt".format(prefix,model_embedding,hnsw_distance))
with open( combinedtraining_file,'wb') as wfd:
    for f in [training_file,study_kgraph_file]:
        with open(f,'rb') as fd:
            shutil.copyfileobj(fd, wfd)

df = None

def train(outfolder,training,epochs=10):
    
    from pykeen.pipeline import pipeline
    result = pipeline(
        training=combinedtraining_file,
        testing=combinedtraining_file,
        model='TransE',
        training_kwargs=dict(num_epochs=epochs),  
    )
    result.save_to_directory(outfolder)

    with open("{}/entity_id_to_label.json".format(outfolder), 'w') as outfile:
        json.dump(result.training.entity_id_to_label, outfile,indent=2)
    with open("{}/relation_id_to_label.json".format(outfolder), 'w') as outfile:
        json.dump(result.training.relation_id_to_label, outfile,indent=2)   
    return result  

import hnswlib
import numpy as np
def ann(embedding_tensor,distance="cosine"):
    dim = np.shape(embedding_tensor)[1]
    num_elements = np.shape(embedding_tensor)[0]

    # Generating sample data
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
from pathlib import Path
import torch
entity_index = os.path.join(folder_output,"pykeen","{}kgraph.hnswlib.index".format(prefix))
if os.path.isfile(entity_index):
    #load
    #e_idx = hnswlib.Index(space=hnsw_distance,dim=768)
    #e_idx.load_index(entity_index )
  
    Path(kg_file).mkdir(parents=True, exist_ok=True)  
    model_file="{}/trained_model.pkl".format(kg_file)

    model = torch.load(model_file)
    
    entity_embedding_tensor = model.entity_representations[0](indices=None).cpu().detach().numpy()
    relation_embedding_tensor = model.relation_representations[0](indices=None).cpu().detach().numpy()
    dim = np.shape(entity_embedding_tensor)[1]
    e_idx = hnswlib.Index(space="cosine",dim=dim)
    e_idx.load_index(entity_index)
else: #train
    result = train(kg_file,training,epochs=500)
    result.plot_losses()
    result.metric_results.to_df()

    entity_embedding_tensor = result.model.entity_representations[0](indices=None).cpu().detach().numpy()
    relation_embedding_tensor = result.model.relation_representations[0](indices=None).cpu().detach().numpy()
    
    e_idx = ann(entity_embedding_tensor)
    e_idx.save_index(entity_index)


    from pykeen.models import predict
    terms = ['http://purl.enanomapper.org/onto/ENM_8000299','http://semanticscience.org/resource/CHEMINF_000228',
            'http://purl.jp/bio/4/id/200906029372903982',   'http://purl.enanomapper.org/onto/ENM_0000084']
    for term in terms:
        print(term)
        try:
            predicted_heads_df = predict.get_head_prediction_df(result.model, 'keyword',term , triples_factory=result.training)
            predicted_heads_df.head()
        except:
            pass

with open("{}/entity_id_to_label.json".format(kg_file), 'r') as infile:
    entity_id_to_label = json.load(infile)
import pandas as pd
df = pd.DataFrame.from_dict(entity_id_to_label,orient='index',columns=["id"])


import numpy as np
from sklearn.decomposition import PCA
pca = PCA(n_components=2)
pca.fit(entity_embedding_tensor)
X = pca.transform(entity_embedding_tensor)
df["x"]=X[:,0]
df["y"]=X[:,1]

#df["type"] = df.apply(lambda x: "term" if x['id'].startswith("http") else ("document" if x['id'].endswith(".pdf") else "study"),axis=1)
df["type"] = df.apply(lambda x: "term" if x['id'].startswith("http") else ("document" if x['id'].endswith(".pdf") else ("study" if x['id'].startswith("NR") else "keyword")),axis=1)

import plotly.express as px
fig = px.scatter(df, x="x", y="y", color="type",  log_x=False, width=1200, height=800,
            hover_name="id", hover_data=["id"]
 )
fig.update_traces(textposition='top center')
fig.update_layout(title_text="xxx", title_x=0.5)
fig.show()


v = pd.DataFrame(entity_embedding_tensor,index=df["id"].values)

findings = []
for i1,row1 in v.iterrows():
    if i1.endswith(".pdf") or i1.startswith("http"): #or (not i1.startswith("NR")):
        continue
    labels,distances =  e_idx.knn_query(row1.values, k=100)
    for label, distance in zip(labels[0],distances[0]):
        if distance > 0.6:
            continue
        _pid = entity_id_to_label[str(label)]
        if i1==_pid:
            continue
        if _pid.endswith(".pdf") :
            #print("{}\t{}\t{}".format(i1,_pid,distance))
            findings.append((i1,_pid,distance,"document"))
        else:
            findings.append((i1,_pid,distance,""))

df = pd.DataFrame(findings,columns=["study","document","distance","type"])
df.to_csv(os.path.join(folder_output,"pykeen","{}kgraph_findings.txt".format(prefix)),sep="\t",index=False)
    
