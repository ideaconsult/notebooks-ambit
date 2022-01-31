# + tags=["parameters"]
upstream = None
folder_output = None
documents = None
scispacy_enable = None
# -

import spacy
import pandas as pd
spacy.prefer_gpu()
from pathlib import Path
import PyPDF2
#import pyate
import os,os.path


#https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemanticTypes_2018AB.txt
#https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemGroups_2018.txt
#https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemanticTypes_2018AB.txt
#https://lhncbc.nlm.nih.gov/ii/tools/MetaMap/Docs/SemGroups_2018.txt

def apply_ner(path,doc, abbreviations,results,links):
    for entity in doc.ents:
        for umls_ent in entity._.kb_ents:
            term=linker.kb.cui_to_entity[umls_ent[0]]
            links.append({
                            "file" : os.path.basename(path),
                            "concept_id" : term.concept_id,
                            "canonical_name" : term.canonical_name.lower(),
            })
            results.append({
                            "concept_id" : term.concept_id,
                            "canonical_name" : term.canonical_name.lower(),
                            "definition" : term.definition,
                            "aliases"    : " ".join(term.aliases),
                            "types" :  " ".join(term.types),
                            "object" : "ENTITY"

                        })
    if abbreviations:
        for abrv in doc._.abbreviations:
            links.append({
                                "file" : os.path.basename(path),
                                "concept_id" : None,
                                "canonical_name" : abrv.text,
            })
            results.append({
                                "concept_id" : None,
                                "canonical_name" : abrv.text,
                                "definition" : abrv._.long_form,
                                "aliases"    : None,
                                "types" :  None,
                                "object" : "ABBREVIATION"
                            })
    return results,links                        

def apply_to_pdf(documents,nlp, abbreviations = True):

    pathlist = Path(documents).glob('**/*.pdf')

    tmp = []
    links = []    
    for path in pathlist:
        pdfObj = open(str(path), 'rb')
        try:
            reader = PyPDF2.PdfFileReader(
                pdfObj,
                strict=True, 
                warndest=None, 
                overwriteWarnings=True
            )
            
            np = reader.getNumPages()
            txt = ""

            for i in range(0, np):
                txt = txt + reader.getPage(i).extractText()
            doc = nlp(txt)
            apply_ner(path,doc, abbreviations,tmp,links)
        except Exception as err:
            print(err)
        finally:
            pdfObj.close()
    return pd.DataFrame(tmp),pd.DataFrame(links)
        

if scispacy_enable:
    import scispacy
    from scispacy.abbreviation import AbbreviationDetector
    from scispacy.linking import EntityLinker
    #import spacy_sentence_bert
    nlp = spacy.load("en_core_sci_sm")
    #nlp = spacy.load("en_core_sci_scibert") #cuda out of memory
    nlp.add_pipe("abbreviation_detector")
    nlp.add_pipe("scispacy_linker", config={"resolve_abbreviations": True, "linker_name": "umls"})
    linker = nlp.get_pipe("scispacy_linker")




    ners = os.path.join(folder_output,"terms","pdf_ner.txt")
    links_file = os.path.join(folder_output,"terms","pdf_nerlinks.txt")
    if (not os.path.exists(ners)) or (not os.path.exists(links_file)):
        df,links = apply_to_pdf(documents,nlp,abbreviations=True)
        df.drop_duplicates(inplace=True)
        links.drop_duplicates(inplace=True)
        df.to_csv(ners,index=False,sep="\t")
        links.to_csv(links_file,index=False,sep="\t")
        
    params = pd.read_csv(os.path.join(folder_output,"params.txt"),sep="\t",encoding="utf-8")
    prms =params["title"].unique()    

    ners = os.path.join(folder_output,"terms","params_ner.txt")
    links_file = os.path.join(folder_output,"terms","params_nerlinks.txt")
    if (not os.path.exists(ners)) or (not os.path.exists(links_file)):
        tmp=[]
        links = []
        for prm in prms:
            doc = nlp(prm)
            apply_ner(prm,doc, True,tmp,links)
        

        
        df = pd.DataFrame(tmp)
        links = pd.DataFrame(links)
        df.drop_duplicates(inplace=True)
        links.drop_duplicates(inplace=True)
        df.to_csv(ners,index=False,sep="\t")
        links.to_csv(links_file,index=False,sep="\t")
    