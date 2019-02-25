import pandas as pd
import logging
import json
import csv
from urllib.parse import urlencode
import urllib3
global logger
logger = logging.getLogger()

from os.path import isfile, join
from requests.auth import AuthBase

_default_ambit="https://apps.ideaconsult.net/nanoreg1" 

class AMBITResource:
    root = None
    resource="/"
    key=""
    
    def __init__(self,root_uri=_default_ambit,resource="/",key=""):
        self.resource=resource
        self.root=root_uri
        self.key=key

           
    def close(self)        :
        self.http.close()
        
    def get(self,http_pool=None,params=None,parse=None):
        if http_pool is None:
            raise
        logger.info("Sending query to %s%s/%s",self.root,self.resource,self.key)
        result = http_pool.request('GET', "{}{}/{}".format(self.root,self.resource,self.key),
                #fields={"q":query['q'], "fl" : query['fl'], "rows": 100000, "fq" : query['fq']},
                headers={
                 'Accept': 'application/json'
                 }                
                 )
        data = json.loads(result.data.decode('utf-8'))
        if (result.status==200):
            #display(data)
            logger.info('Received response ')
   
            logger.debug(json.dumps(data, indent=2))
            
            try:
                if parse!=None:
                    return parse(data)   
                else:
                    return data
            except Exception as err:
                print(err)

        else:
            logger.error(result.status)
            logger.debug(data)
        return   

         
class AMBITSubstance(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/substance",key=""):
         super().__init__(root_uri,resource,key)   
            
class AMBITQuery(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/query",key="/study"):
         super().__init__(root_uri,resource,key)

class AMBITSolr(AMBITResource):
    
    def __init__(self,root_uri=_default_ambit,resource="/solr",key="/study"):
         super().__init__(root_uri,resource,key)            
            

class AmbitAPIKEYAuth(AuthBase):
    """Authorization: APIKEY XXXX"""
    def __init__(self, apikey):
        self.apikey = apikey

    def __call__(self, r):
        r.headers['Authorization'] = "APIKEY {}".format(self.apikey)
        return r            