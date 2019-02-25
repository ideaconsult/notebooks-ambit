import pandas as pd
import logging
import json
import csv
from urllib.parse import urlencode
import urllib3

from os.path import isfile, join

def getSolrQuery(settings,url=None):
    
    studyfilter=''
    if settings['studyfilter'] != None:
        studyfilter = "AND {}".format(settings['studyfilter'])
        
    if settings['endpointfilter'] != None:
        endpointfilter = "AND {}".format(settings['endpointfilter'])
  
    paramsFilter = ' OR filter(type_s:params {})'.format(studyfilter)
    conditionsFilter = ' OR filter(type_s:conditions {})'.format(studyfilter)
    compositionFilter='OR filter(type_s:composition AND component_s:CONSTITUENT)'
    
    #monoconstituentFilter = " AND substanceType_s:(mono constituent substance)"
    
    fl = 'name_hs,publicname_hs,substanceType_hs,s_uuid_hs,[child parentFilter=filter(type_s:substance) childFilter="filter(type_s:study {} {}) {} {} {}" limit=10000]'.format(studyfilter,endpointfilter,paramsFilter,conditionsFilter,compositionFilter)

    return {
        'url': url,
        'fl' : fl,
    #    'fl' : 'name_hs,substanceType_hs,s_uuid_hs,[child parentFilter=filter(type_s:substance) childFilter="filter(type_s:study AND '+ settings['studyfilter']  +') OR filter(type_s:composition AND component_s:CONSTITUENT) OR filter(type_s:PARAMS AND '+settings['studyfilter']+') OR filter(type_s:CONDITIONS AND '+settings['studyfilter']+' limit 100000)"]',    
         #'fq' :'substanceType_hs:(MONO CONSTITUENT SUBSTANCE)',
         'fq' : '',
         'q' : '{!parent which=type_s:substance}'
    }


def parseSolrRequest(settings,docs,rows):
    
    logger= logging.getLogger()
    logger.debug("Parsing solr resposne")
    record=0
    #print(docs)
            
    for doc in docs:
      
        record=record+1
        
        if record==1:
            logger.info(json.dumps(doc, indent=2))
        
        params = {}            
        conditions = {} 
        cas = {}
        einecs = {}

        if (not '_childDocuments_' in doc):
            continue
        
        
        for childdoc in doc['_childDocuments_']:
            if (childdoc['type_s'] == 'composition'):
                if (childdoc['component_s'] == "CONSTITUENT"):
                    try:
                        caskey=childdoc['CASRN_s']
                        cas[caskey] =  childdoc['component_s']
                    except:
                        pass  # val does not exist at all
                    try:
                        ekey=childdoc['EINECS_s']
                        einecs[ekey] =  childdoc['component_s']
                    except:
                        pass  # val does not exist at all
                
                

            if (childdoc['type_s'] == 'params'):    
                #display(childdoc)    
                params[childdoc['document_uuid_s']]= childdoc 
                
            if (childdoc['type_s'] == 'conditions'):    
                 conditions[childdoc['effectid_hs']]= childdoc 


        for childdoc in doc['_childDocuments_']:

            if (childdoc['type_s'] == 'study'):
                
                try: 
                    #print('{}\t{:s}\t{:s}\t{:s}'.format(record,doc['s_uuid_hs'],doc['substanceType_hs'],doc['name_hs']))
                    #print(json.dumps(childdoc, indent=2))
                    pass
                except:
                    pass                  
                #print(doc['name_hs'],'\t',doc['substanceType_hs'])
                doc_uuid = childdoc['document_uuid_s']
                study_id= childdoc['id']
                upValue=None
                loValue=None
                exposure_h=None
                reliability=None
                loQualifier=''
                upQualifier=''
                test_organism=None
                guidance=''
                effectendpoint = ''
                effectendpoint_type = ''
                studyResultType=''
                reference_year=''
                s_uuid=''
                document_uuid=''
                Measured_concentration=''
                purposeFlag=''
                
                try:
                    reliability = childdoc['reliability_s']
                except :
                    pass  
                
                try:
                    studyResultType = childdoc['studyResultType_s']
                except :
                    pass        
                
                try:
                    studyResultType = childdoc['studyResultType_s']
                    
                except :
                    pass 

#experimental result
#no data
#other:
#read-across based on grouping of substances (category approach)
#read-across from supporting substance (structural analogue or surrogate)
#(blank)
                #skip the most obvious crap    
                try:
                    purposeFlag = childdoc['purposeFlag_s']
                except :
                    pass      
                
                try:
                    s_uuid = childdoc['s_uuid_s']
                except :
                    pass                       

                try:
                    document_uuid = childdoc['document_uuid_s']
                except :
                    pass                       
                
                try:
                    reference_year = childdoc['reference_year_s']
                except :
                    pass 
                
                try:
                    effectendpoint = childdoc['effectendpoint_s']
                except :
                    pass  
                try:
                    effectendpoint_type = childdoc['effectendpoint_type_s']
                except :
                    pass  
                
                
                try:
                    guidance = str(childdoc['guidance_s'])
                except :
                    pass  
                
                   
                try:
                    loValue = childdoc['loValue_d']
                except :
                    pass          
                #if (loValue is None):
                #    continue
            
                try:
                    upValue = childdoc['upValue_d']
                    #print(json.dumps(childdoc, indent=2))
                        
                except :
                    upValue=""
                    
                try:
                    loQualifier = childdoc['loQualifier_s']
                except :
                    loQualifier=""
                    
                try:
                    upQualifier = childdoc['upQualifier_s']
                except :
                    upQualifier=""
                    
                try:
                    unit = childdoc['unit_s']
                except :
                    unit=""                    
                '''    
                try:
                    exposure_h = conditions[study_id]['Exposure_h_s']
                except :
                    exposure_h=""
                    
                try:
                    exposure_d = conditions[study_id]['Exposure_d_s']
                except :
                    exposure_d=""
                '''
                
                #sorry we want to know what the value means
                if (effectendpoint == ''):
                    logger.warning('Removed because of empty endpoint')
                    continue                
                
                substance_uuid = doc['s_uuid_hs']
                
                substancetype = None
                try:
                    substancetype=doc['substanceType_hs']
                except:
                    substancetype = None
                    
                row={'substance.name' : doc['name_hs'], 
                     'public.name' : doc['publicname_hs'], 
                     #'substance.uuid' : substance_uuid, 
                     'substance.uuid' : s_uuid,
                     'substance.type' : substancetype, 
                     'x.oht.top' : childdoc['topcategory_s'],
                     'x.oht.section' : childdoc['endpointcategory_s'],
                     'x.guidance' : guidance,
                     'value.endpoint' : effectendpoint,
                     'value.endpoint_type' : effectendpoint_type,
                     'value.qualifier.lo' : loQualifier,
                     'value.qualifier.up' : upQualifier,
                     'value.lo' : loValue,
                     'value.up' : upValue,
                     'value.unit' : unit,
                     'r.reliability' : reliability,
                     #'x.params.test_organism' : test_organism,
                     #'Exposure_d' : exposure_d,
                     #'Exposure_h' : exposure_h,
                     'r.studyResultType' : studyResultType,
                     'r.purposeFlag' : purposeFlag,
                     
                     'x.document_uuid' : document_uuid,
                     'x.reference_year' : reference_year
                    }
                
                try:
                    for condition in conditions[study_id]:
                        if condition == "type_s" or condition=="document_uuid_s" or condition=="id" or condition=="topcategory_s" or condition=="endpointcategory_s":
                            continue
                        row["x.conditions." + condition.replace("_s","")] = conditions[study_id][condition]
                except:
                    pass
                try:
                    for prm in params[document_uuid]:
                        if prm == "type_s" or prm=="document_uuid_s" or prm=="id" or prm=="topcategory_s" or prm=="endpointcategory_s":
                            continue
                        row["x.params."+prm.replace("_s","")] = params[document_uuid][prm]
                except:
                    pass
                    
                try:
                    fields = settings["fields"]["conditions"]
                    for field in fields:
                        key="x.conditions." + field.replace("_s", "")
                        value = conditions[study_id][field]
                        if pd.isna(value):
                            value=''
                        row[key] = value
                except:
                    pass
                
                try:
                    fields = settings["fields"]["params"]
                    for field in fields:
                        key="x.params."+field.replace("_s", "")
                        value = params[doc_uuid][field]
                        if pd.isna(value):
                            value=''
                        row[key] = value
                except :
                    pass 
                
                for key,value in cas.items():
                    row['c.CAS']=key
                for key,value in einecs.items():
                    row['c.EINECS']=key    

                
                rows.append(row)    
    return (rows)

# http://urllib3.readthedocs.io/en/latest/user-guide.html
#basic_auth = 'abc:xyz'
def sendSolrRequest(settings,http,textfilter,query,rows, basic_auth=None):
        if basic_auth==":" or basic_auth=="":
            basic_auth=None
        logger= logging.getLogger()
        
        if textfilter==None:
            query['q']='{!parent which=type_s:substance}'
        else:    
            query['q']='{!parent which=type_s:substance}('+textfilter+')'
            
        logger.info("Sending query to %s",query['url'])
        if basic_auth is None:
            headers={}
        else:
            headers = urllib3.util.make_headers(basic_auth=basic_auth)
        result = http.request('POST', query['url'],
                fields={"q":query['q'], "fl" : query['fl'], "rows": 100000, "fq" : query['fq'],"wt" : 'json'},
                headers=headers              
                 )
        if (result.status==200):
            data = json.loads(result.data.decode('utf-8'))            
            #display(data)
            #logger.info('Received response found {:d} docs {:d}'.format(data['response']['numFound'],len(data['response']['docs'])))
   
            #logger.debug(json.dumps(data, indent=2))

            try:
                return parseSolrRequest(settings,docs=data['response']['docs'],rows=rows)    
            except Exception as err:
                print(err)

        else:
            logger.error(result.status)
            
        return     
    
def getSubstanceComposition(http,ambit_url,substance_uuid):
        logger= logging.getLogger()
        #url = (ambit_url + "/query/compound/search/all?search=" + substance_uuid + "&media=application/json")
        url = (ambit_url + "/substance/" + substance_uuid + "/composition?media=application/json")
        result = http.request('GET', url )
        #logger.debug(url)        
        if (result.status==200):
            composition = json.loads(result.data.decode('utf-8'))
            return composition
        else:
            logger.error(result.status)
            return None
        
def getCompoundIdentifiers(http,ambit_url,compound_uri):
        logger= logging.getLogger()
        x = compound_uri.find("/conformer")
        if x>0:
            compound_uri= compound_uri[:x]
            
        #params = urlencode({"search": compound_uri, "media" : "chemical/x-daylight-smiles"})
        
        #params = urlencode({"search": compound_uri, "media" : "application/json" , "type" : "auto"})
        #url = (ambit_url + "/query/compound/url/all?" + params)
        
        params = urlencode({ "media" : "chemical/x-mdl-sdfile"})
        #params = urlencode({ "media" : "chemical/x-daylight-smiles"})
        url = (compound_uri + "?" +  params)
        result = http.request('GET', url)        
        
        if (result.status==200):
            return result.data.decode("utf-8") 
        else:
            logger.error(result.status)
            return None        
        
            
            
_fields = {}
"""
_fields["TO_BIODEG_WATER_SCREEN_SECTION"] = {"conditions" : ["Sampling time_d_s"], "params" : ["Test type_s"]}
_fields["EN_HENRY_LAW_SECTION"] = {"conditions" : ["Temperature_℃C_s","Pressure_hPa_s"], "params" : []}
_fields["PC_PARTITION_SECTION"] = {"conditions" : ["Temperature_\u00b0C_s","pH_s"], "params" : ["Method type_s"]}
_fields["PC_WATER_SOL_SECTION"] = {"conditions" : ["Temperature_\u00b0C_s","pH_s"], "params" : ["Method type_s"]}
_fields["EC_CHRONFISHTOX_SECTION"] = {"conditions" : ['Measured concentration_s','Exposure_h_s','Exposure_d_s'], "params" : ['Test organism_s']}
_fields["EC_FISHTOX_SECTION"] = {"conditions" : ['Measured concentration_s','Exposure_h_s','Exposure_d_s'], "params" : ['Test organism_s']}
_fields["EC_CHRONDAPHNIATOX_SECTION"] = {"conditions" : ['Measured concentration_s','Exposure_h_s','Exposure_d_s','Based on_s','Effect_s'], "params" : ['Test organism_s','Test Medium_s']}
_fields["EC_DAPHNIATOX_SECTION"] = {"conditions" : ['Measured concentration_s','Exposure_h_s','Exposure_d_s'], "params" : ['Test organism_s']}
_fields[""] = None
"""

_endpoint = {}
_endpoint[""] = "*"
_endpoint["EC_CHRONFISHTOX_SECTION"] = 'LC50'
_endpoint["EC_FISHTOX_SECTION"] = 'LC50'
                