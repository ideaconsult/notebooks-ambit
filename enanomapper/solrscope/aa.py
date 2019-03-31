from requests.auth import AuthBase
import requests
import pandas as pd
import yaml
from pandas.io.json import json_normalize

class AmbitAPIKEYAuth(AuthBase):
    """Authorization: APIKEY XXXX"""
    def __init__(self, apikey):
        self.apikey = apikey

    def __call__(self, r):
        r.headers['Authorization'] = "APIKEY {}".format(self.apikey)
        return r   
    
class GraviteeAuth(AuthBase):
    def __init__(self, apikey):
        self.apikey = apikey

    def __call__(self, r):
        r.headers['X-Gravitee-Api-Key'] = self.apikey
        return r       
    
    
def parseOpenAPI3(url='https://search.data.enanomapper.net/api-docs/', config='solr.yaml',auth="enmKeyAuth"):
    apikey=None
    config = yaml.load(requests.get(url+config).text)
    config_servers = json_normalize(config['servers'], None, ['url'])
    if 'securitySchemes' in config['components']:
        config_security = json_normalize(config['components']['securitySchemes'], None, [])
        try:
            apikey=config_security['{}.name'.format(auth)][0]    
        except:
            apikey=None
    else:
        config_security = None
        
    return config,config_servers, apikey
    
def operationAuth(config,path='/select',method='get',auth="enmKeyAuth"):
    operation = config['paths'][path]['get']['security']
    return [apikey for item in operation if auth in item]    