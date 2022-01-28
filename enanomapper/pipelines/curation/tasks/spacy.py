# + tags=["parameters"]
upstream = None
folder_output = None
model_embedding = None
hnsw_distance = None
documents = None
# -

import hnswlib
import spacy
from spacypdfreader import pdf_reader 
import os, os.path
import torch

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
from sentence_transformers import SentenceTransformer
    #distilbert-base-nli-stsb-mean-tokens for symmetric search

model = SentenceTransformer(model_embedding, device=torch_device)
e_idx = hnswlib.Index(space=hnsw_distance,dim=768)
e_idx.load_index(ann_index )

spacy.prefer_gpu()




import pandas as pd
terms_file = os.path.join(folder_output,"terms","terms.txt")
terms = pd.read_csv(terms_file,sep="\t",encoding="utf-8")

def get_nouns(doc):
    nouns = {}
    for chunk in doc.noun_chunks:
        query = chunk.text.replace("\n"," ").replace("\r"," ").replace("."," ").replace("  "," ").strip().lower()
        try:
            float(query)
            continue
        except:
            pass
        if len(query)<2:
            continue
        elif query in nouns:
            nouns[query] = nouns[query]+1
        else:
            nouns[query] = 1
    return nouns
def analyse_doc(terms,model,e_idx,doc_terms,file,output_f,nhits=3):


    try: 
        print("Noun phrases:")
        for noun in doc_terms.keys():
            query = noun
            if len(query)<2:
                continue
            embeddings = model.encode(query, 
                            show_progress_bar=False,
                            normalize_embeddings=True)

            labels,distances =  e_idx.knn_query(embeddings, k=nhits)
            rank = 1
            for label, distance in zip(labels[0],distances[0]):
                if distance<0.25:
                    output_f.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format(file,query,doc_terms[query],rank,distance,terms.iloc[label]["Class ID"],terms.iloc[label]["Preferred Label"],terms.iloc[label]["Definitions"]))
                    rank=rank+1
            output_f.flush()
    except Exception as err:
        print(err)


#print("Verbs:", [token.lemma_ for token in doc if token.pos_ == "VERB"])

# Find named entities, phrases and concepts
#for entity in doc.ents:
#    print(entity.text, entity.label_)
from pathlib import Path
import PyPDF2
def annotate_terms(documents,terms,model,e_idx,ann_hits):

    pathlist = Path(documents).glob('**/*.pdf')
    nlp = spacy.load("en_core_web_sm")
    ann_hits = os.path.join(folder_output,"terms","{}_{}_pdf_hits.txt".format(model_embedding,hnsw_distance))
    with open(ann_hits, 'w',encoding='utf-8') as output_f:
        output_f.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format("file","query","count","rank","distance","id","label","definition"));

        for path in pathlist:
            pdfObj = open(str(path), 'rb')
            try:
                reader = PyPDF2.PdfFileReader(
                    pdfObj,
                    strict=True, 
                    warndest=None, 
                    overwriteWarnings=True
                    )
                print(reader.documentInfo)
                np = reader.getNumPages()
                txt = ""
                for i in range(0, np):
                    txt = txt + reader.getPage(i).extractText()
                doc = nlp(txt)
                nouns = get_nouns(doc) 
                analyse_doc(terms,model,e_idx,nouns,os.path.basename(str(path)),output_f)
            except Exception as err:
                print(err)
            finally:
                pdfObj.close()

#annotate_nounphrases(documents,folder_output,model_embedding,hnsw_distance,terms):

def annotate_nounphrases(documents,terms,model,e_idx,ann_hits):
    
    pathlist = Path(documents).glob('**/*.pdf')
    nlp = spacy.load("en_core_web_sm")

    with open(ann_hits, 'w',encoding='utf-8') as output_f:
        output_f.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format("file","query","count","rank","distance","id","label","definition"));

        for path in pathlist:
            file = os.path.basename(str(path))
            doc = pdf_reader(str(path), nlp)        
            nouns = get_nouns(doc)    
            analyse_doc(terms,model,e_idx,nouns,file,output_f,nhits=2)

ann_hits = os.path.join(folder_output,"terms","{}_{}_pdf_hits.txt".format(model_embedding,hnsw_distance))
#annotate_nounphrases(documents,terms,model,e_idx,ann_hits)
annotate_terms(documents,terms,model,e_idx,ann_hits)