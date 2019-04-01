from jproperties import Properties
import os, os.path

class Dictionary:

    def __init__(self,folder = './annotation/', topic='endpoint'):
        self.lookup = Properties()
        self.topic=topic
        self.folder = folder
        self.loadDictionary()
        
    def loadDictionary(self):
        prop_file= self.folder + self.topic + ".properties"
        try:
            with open(prop_file, "rb") as f:
                self.lookup.load(f, "utf-8") 

        except Exception as err:
            self.lookup = None
            print(err)
            
    def annotate(self,x):
        if self.lookup is None:
            return None
        x=x.replace(" ","_").upper().strip()

        if x in self.lookup:
            value, meta = self.lookup[x]
            return value
        else:
            return None       
        
    def getLink(self,ontouri):
        if ontouri.startswith("http"):
            return "http://bioportal.bioontology.org/ontologies/ENM/?p=classes&conceptid=" + ontouri
        else:
            return None
        
   
class DictionaryEndpoints(Dictionary):    
    def __init__(self,folder = './annotation/', topic='endpoint'):
        super().__init__(folder = './annotation/', topic='endpoint')
            
class DictionaryAssays(Dictionary):    
    def __init__(self,folder = './annotation/', topic='assays'):
        super().__init__(folder = './annotation/', topic='assays')            
            
class DictionaryCells(Dictionary):    
    def __init__(self,folder = './annotation/', topic='cells'):
        super().__init__(folder = './annotation/', topic='cells')               
        
class DictionaryEndpointCategory(Dictionary):    
    def __init__(self,folder = './annotation/', topic='endpointcategory'):
        super().__init__(folder = './annotation/', topic='endpointcategory')                       

class DictionarySpecies(Dictionary):    
    def __init__(self,folder = './annotation/', topic='species'):
        super().__init__(folder = './annotation/', topic='species')       

class DictionarySubstancetypes(Dictionary):    
    def __init__(self,folder = './annotation/', topic='substancetype'):
        super().__init__(folder = './annotation/', topic='substancetype')                                       