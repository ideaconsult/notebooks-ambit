from jproperties import Properties
import os, os.path

class Dictionary:
    
    def __init__(self,folder = './annotation/', topic='endpoint',verbose=True):
        self.lookup = Properties()
        self.topic=topic
        self.folder = folder
        self.verbose=verbose
        self.loadDictionary()
        
    def loadDictionary(self):
        suffix = ".properties"
        if self.verbose:
            suffix = ".properties"
        else:
            suffix = ".terse.properties"
        prop_file= self.folder + self.topic + suffix
        try:
            with open(prop_file, "rb") as f:
                self.lookup.load(f, "utf-8") 

        except Exception as err:
            self.lookup = None
            print(err)
            
    def annotate(self,x):
        if self.lookup is None:
            return None
        try:
            x_=x.replace(" ","_").replace("\t","").upper().strip()

            if x in self.lookup:
                value, meta = self.lookup[x_]
                return value
                
            else:
                return x      
        except:
            return None
        
    def getLink(self,ontouri):
        if ontouri.startswith("http"):
            return "http://bioportal.bioontology.org/ontologies/ENM/?p=classes&conceptid=" + ontouri
        else:
            return None
        
   
class DictionaryEndpoints(Dictionary):    
    def __init__(self,folder = './annotation/', topic='endpoint'):
        super().__init__(folder = './annotation/', topic='endpoint',verbose=True)
            
class DictionaryAssays(Dictionary):    
    def __init__(self,folder = './annotation/', topic='assays'):
        super().__init__(folder = './annotation/', topic='assays',verbose=True)            
            
class DictionaryCells(Dictionary):    
    def __init__(self,folder = './annotation/', topic='cells'):
        super().__init__(folder = './annotation/', topic='cells',verbose=True)               
        
class DictionaryEndpointCategory(Dictionary):    
    def __init__(self,folder = './annotation/', topic='endpointcategory'):
        super().__init__(folder = './annotation/', topic='endpointcategory',verbose=True)                       

class DictionaryEndpointCategoryNames(Dictionary):    
    def __init__(self,folder = './annotation/', topic='endpointcategory_names'):
        super().__init__(folder = './annotation/', topic='endpointcategory_names',verbose=True)  
        
class DictionarySpecies(Dictionary):    
    def __init__(self,folder = './annotation/', topic='species'):
        super().__init__(folder = './annotation/', topic='species',verbose=True)       

class DictionarySubstancetypes(Dictionary):    
    def __init__(self,folder = './annotation/', topic='substancetype',verbose=True):
        super().__init__(folder = './annotation/', topic='substancetype',verbose=verbose)                                       