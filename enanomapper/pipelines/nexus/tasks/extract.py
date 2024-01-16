# + tags=["parameters"]
upstream = None
enm_api_url = None
enm_api_key = None
folder_output = None
query = None
product = None
db = None
# -

from pynanomapper import aa
import os, os.path
import pandas as pd
import requests 
import  pynanomapper.datamodel.ambit as m2n
from pynanomapper.datamodel.nexus_writer import to_nexus
import nexusformat.nexus.tree as nx
import traceback

def json2nexus(url_db,auth,pjson):
    substances = m2n.Substances(**pjson)
    for substance in substances.substance:
        try:
            print(substance)
            url = "{}/substance/{}/study&media=application/json&max={}".format(url_db,substance.i5uuid,10000)
            #url = "{}/study?media=application/json&max=10000".format(substance.URI)
            response = requests.get(url,auth=auth)
            if response.status_code ==200:
                print(substance.i5uuid)
                sjson = response.json()
                print(sjson)
                substance.study = m2n.Study(**sjson).study
            else:
                print(response.status_code,url)
        except Exception as err:    
            print(url,err)
 
    return substances


config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3() 
if auth_object!=None:
    auth_object.setKey(enm_api_key)  

rows = 1000
url_db = "{}/enm/{}/substance?{}&media=application/json&max={}".format(enm_api_url,db,query,rows)

response = requests.get(url_db,auth=auth_object)
if response.status_code ==200:
    #print(response.text)
    pjson = response.json()
    print(pjson)
    nxroot = nx.NXroot()
    substances = json2nexus("{}/enm/{}".format(enm_api_url,db),auth_object,pjson)
    substances.to_nexus(nxroot)
    nxroot.save(os.path.join(folder_output,"substances.nxs"),mode="w")
else:
    print(response.status_code)

    