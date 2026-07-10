import os.path
import requests
import pandas as pd

class Vocabulary:
    
    def __init__(self,folder,subfolder = "terms",bioportal_apikey=None):
        self.folder = folder
        self.subfolder = subfolder
        self.bioportal_apikey = bioportal_apikey



    def load_ontology(self,url="https://data.bioontology.org/ontologies/ENM/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb&download_format=csv",
                    onto_file='enm.csv.gz',usecols=None, synonyms_sep=None,synonyms_fields=["Synonyms"],definition_fields=["Definitions"]):
        
        onto_file = os.path.join(self.folder,self.subfolder,onto_file)
        if not os.path.isfile(onto_file):
            print(url)
            try:
                enmfile = requests.get(url)
                if enmfile.status_code == 200:
                    open(onto_file, 'wb').write(enmfile.content)
                else:
                    raise(requests.exceptions.RequestException(enmfile.status_code))
            except Exception as err:
                raise(err)
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
        
        url="https://data.bioontology.org/ontologies/{}/download?apikey={}&download_format=csv".format(onto_name,self.bioportal_apikey)
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
