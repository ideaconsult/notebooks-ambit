import pandas as pd
import logging
import json
import csv
import requests
global logger
logger = logging.getLogger()

from os.path import isfile, join
from requests.auth import AuthBase

_default_ambit="https://apps.ideaconsult.net/nanoreg1" 

class AMBITResource:
    root = None
    resource="/"
    key=None
    
    def __init__(self,root_uri=_default_ambit,resource="/",key=None):
        self.resource=resource
        self.root=root_uri
        self.key=key
    
    def uricompose(self):
        url = self.root
        if self.resource != None:
            url = url + self.resource
        if self.key != None:
            url = url + self.key
        return url
    
    def get(self,params=None, media="application/json",page=0,pagesize=10,auth=None,verbose=False):
        url = self.uricompose()
        params = self.getParams(params,page,pagesize,media)            
        if verbose:
            print("Sending request to {} params {}".format(url,params))
        r = requests.get(url,params=params, auth=auth)
        return r           
        
    def getParams(self,params=None,page=0,pagesize=10,media="application/json"):
        if params is None:
            params={}
        params['media'] = media    
        params['page']=page
        params['pagesize']=pagesize
        return params
    
    def parse(self,response):
        return response
         
class AMBITSubstance(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/substance",key=None):
         super().__init__(root_uri,resource,key)   
            
    def parse(self,response):
        return response['substance']            
            
class AMBITSubstanceComposition(AMBITResource):
    
    def __init__(self,root_uri,resource="/composition",key=None):
         super().__init__(root_uri,resource,key)  

    def parse(self,response):
        return response['composition']     
    
class AMBITSubstanceStudy(AMBITResource):
    
    def __init__(self,root_uri,resource="/study",key=None):
         super().__init__(root_uri ,resource,key)  
    
    def parse(self,response):
        return response['study']                
    
class AMBITInvestigation(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/investigation",key=None):
         super().__init__(root_uri,resource,key)   
            
    
    def parse(self,response):
        return response['results']                
                
            
class AMBITCompound(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/compound",key=None):
         super().__init__(root_uri,resource,key) 
            
    def uricompose(self):
        url = super().uricompose()
        return url.split("/conformer")[0]
      
            
class AMBITTask(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/task",key=None):
         super().__init__(root_uri,resource,key)        
            
class AMBITAlgorithm(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/algorithm",key=None):
         super().__init__(root_uri,resource,key)       

class AMBITModel(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/model",key=None):
         super().__init__(root_uri,resource,key)                         
              
class AMBITQuery(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/query",key="/study"):
         super().__init__(root_uri,resource,key)
            
class AMBITQueryCompound(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/query",key="/compound/search/all"):
         super().__init__(root_uri,resource,key)
            
#  /query/compound/search/all?type=auto&search=2825-82-3&page=0&pagesize=1&media=application/json            
    def search(self,search_value,search_type='auto',media='chemical/x-mdl-sdfile',page=0,pagesize=10,auth=None):
        params={}
        params['type'] = search_type
        params['search'] = search
        return self.get(params=params, media="application/json",page=page,pagesize=pagesize,auth=auth)   
            
          

class AMBITFacets(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/query",key="/study"):
         super().__init__(root_uri,resource,key)            
    def parse(self,response):
        return response['facet']              
   
            