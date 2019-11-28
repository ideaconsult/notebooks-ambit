import requests
import yaml
import pandas as pd
import numpy as np
import logging
from pandas.io.json import json_normalize
global logger
logger = logging.getLogger()
import json
from solrscope import annotation

def post(service_uri,query,auth=None):
    r = requests.post(service_uri + "/select",data=query, auth=auth)
    return r

def get(service_uri,query,auth=None):
    r = requests.get(service_uri + "/select",params=query, auth=auth)
    return r


class Facets:

    def getQuery(self,query='*:*',facets=["endpointcategory_s","effectendpoint_s","unit_s"],fq='', rows=0):
        json_facet = self.getNestedFacets(facets);
        query={'q': query,'fq' : fq, "wt" : "json", "json.facet": json_facet, 'rows': rows}
        return query

    def parse(self,facets,key="ALL",prefix="",process=None,_tuple=()):
        count = facets['count']
        if 'val' in facets:
            val = facets['val']            
        else:
            val='_'
        if process is None:    
            print("{}\t{}'{}'\t{}\t{}".format(prefix,_tuple,val,count,key)) 
        else:
            process(prefix,val,count,key,_tuple)
        if facets== None:
            return
        for f in facets.keys():
            key = None
            if 'count'==f:
                continue
            elif 'val'==f:
                continue
            else:
                key=f
                for bucket in facets[f]['buckets']:
                    self.parse(bucket,key,prefix+"\t",process,(*_tuple,val))
                if facets[f]['missing']['count'] >0:
                    self.parse(facets[f]['missing'],key,prefix+"\t",process,(*_tuple,val))

    def getFacet(self,field="endpointcategory_s",n=1,nested=None):
        fieldname="field{}".format(n)
        if nested==None:
            nested_facet=""
        else:    
            nested_facet= ", facet:" + nested 
        return "{" + fieldname + ": {"+ "{}:{},{}:{} ,limit : -1, mincount:1, missing:true ".format("type","terms","field",field) +nested_facet + "}}"


    def getNestedFacets(self,facets=["endpointcategory_s","effectendpoint_s","unit_s"]):
        if facets is None:
            return ''
        
        n=len(facets)
        if n==1:
            nested_facet=None
        else:    
            nested_facet = self.getNestedFacets(facets[1:len(facets)])
        facet = self.getFacet(facets[0],n,nested_facet)
        return facet

        
    #json_facet="{field1: {" + "{}:{},{}:{} ,limit : -1, mincount:1 ".format("type","terms","field",field1) + field2_facet + " }}"

    #query={'q': query,"wt" : "json", "json.facet": json_facet, 'rows': 0}
    #return query

    def parseFacet2(self,response_json,key1 = "field1",key2 = "field2"):
        fields = response_json["facets"][key1]["buckets"]
        fields_name=[]
        fields_count=[]
        field_2=[]
        for value in fields:
            fields_name.append(value['val'])
            fields_count.append(value['count'])
            _field2=''
            try:
                for item in value[key2]['buckets']:
                    if item['val'].startswith("EP_"):
                        continue
                    _field2 = _field2 + " " + item['val']

            except Exception as err:
                pass
            field_2.append(_field2.strip())    

        return pd.DataFrame({key1 : fields_name, "count" : fields_count, key2 : field_2})
    
    def summary(this,service_uri,auth_object,query="*:*",fq="type_s:study",statistics="Number of data points",fields=["topcategory_s","endpointcategory_s","E.method_s","substanceType_s","publicname_s","reference_owner_s"],log_query=None,log_result=None):
        colnames=["Z"]
        colnames.extend(fields)
        colnames.append(statistics)
        _stats=[]
        def process(prefix,val,count,key,_tuple):
            if len(_tuple)==len(fields):
                _tuple = (*_tuple,val,count)
                _stats.append(_tuple)
        q=this.getQuery(query=query,facets=fields,fq=fq)
        if log_query!=None:
            log_query(q)

        r = post(service_uri,query=q,auth=auth_object)
        response_json=r.json()

        if r.status_code==200:
            if log_result!=None:
                log_result(response_json)
            this.parse(response_json['facets'],prefix=">",process=process)
            df = pd.DataFrame(_stats,columns=colnames).drop("Z", axis=1)
            if "substanceType_s" in df.columns:
                a = annotation.DictionarySubstancetypes()
                df[ 'substanceType_name']=df[ 'substanceType_s'].apply(a.annotate)
            if "substanceType_hs" in df.columns:
                a = annotation.DictionarySubstancetypes()
                df[ 'substanceType_name']=df[ 'substanceType_hs'].apply(a.annotate)            
            if "endpointcategory_s" in df.columns:    
                a = annotation.DictionaryEndpointCategory()
                df[ 'endpointcategory_term']=df[ 'endpointcategory_s'].apply(a.annotate)
                a = annotation.DictionaryEndpointCategoryNames()
                df[ 'endpointcategory_name']=df[ 'endpointcategory_s'].apply(a.annotate)

            if "method_term" in df.columns:
                a = annotation.DictionaryAssays()
                df[ 'method_term']=df[method_field].apply(a.annotate)
            return (df)
        else:
            print(r.status_code)
            return (None)           

class StudyDocuments:    
    
    def __init__(self):
        #settings['query_organism']="Daphnia magna"  
        #settings['studyfilter']=' topcategory_s:ECOTOX AND endpointcategory_s:EC_DAPHNIATOX_SECTION AND guidance_s:OECD_TG_202 '
        #settings['endpointfilter']= ' effectendpoint_s:LC50 '        
        self.settings={}
        self.settings['studyfilter'] = None
        self.settings['query_organism'] = None
        self.settings['endpointfilter'] = None
        self.settings['query_guidance'] = None
        self.settings['fields'] = None
        
    def getSettings(self):
        return self.settings
    
    def setStudyFilter(self,filter = {'topcategory_s':'ECOTOX', 'endpointcategory_s':'EC_FISHTOX_SECTION','guidance_s':'OECD_TG_203'}, combineas = 'AND' ):       
        self.settings['studyfilter'] =''   
        sep=' '
        for i in filter:
            self.settings['studyfilter'] = self.settings['studyfilter'] + ' {} {}:{}'.format(sep,i,filter[i])
            sep= combineas
        return self.settings['studyfilter']

    def getQuery(self,textfilter=None,facets=None,fq='', rows=10, _params=True, _conditions=True, _composition=False ):
    
        studyfilter=''
        if self.settings['studyfilter'] != None:
            studyfilter = "AND {}".format(self.settings['studyfilter'])

        if self.settings['endpointfilter'] != None:
            endpointfilter = "AND {}".format(self.settings['endpointfilter'])
        else:
            endpointfilter=''

        if _params:    
            paramsFilter = ' OR filter(type_s:params {})'.format(studyfilter)
        else:
            paramsFilter=''
        if _conditions:
            conditionsFilter = ' OR filter(type_s:conditions {})'.format(studyfilter)
        else:
            conditionsFilter=''
        if _composition:
            compositionFilter='OR filter(type_s:composition AND component_s:CORE)'
        else:
            compositionFilter=''

        #monoconstituentFilter = " AND substanceType_s:(mono constituent substance)"

        fl = 'dbtag_hss,name_hs,publicname_hs,substanceType_hs,owner_name_hs,s_uuid_hs,[child parentFilter=filter(type_s:substance) childFilter="filter(type_s:study {} {}) {} {} {}" limit=10000]'.format(studyfilter,endpointfilter,paramsFilter,conditionsFilter,compositionFilter)

        if textfilter==None:
            query='{!parent which=type_s:substance}'
        else:    
            query='{!parent which=type_s:substance}('+textfilter+')'
            
        if facets is None:
            json_facet = ''
        else:
            json_facet = Facets().getNestedFacets(facets);
            
        query={'q': query,'fq' : fq, "wt" : "json", 'fl' : fl, "json.facet": json_facet, 'rows': rows}
        return query
    def rows2frame(self,rows):
        df = pd.DataFrame(rows)
        #df = df.replace(np.nan, '', regex=True)
        for prefix in ['db','m.','p.','uuid.','value.endpoint','value.range.lo.qualifier','value.range.up.qualifier','value.uncertainty_type','value.unit','x.','xR.']:
            filter_col = [col for col in df if col.startswith(prefix)]
            for col in filter_col:
                df[col] = df[col].astype('category')
        return df
    
    def parse(self,docs):
        rows=[]
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
                    if (childdoc['component_s'] == "CORE"):
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
                    quality_remark=[]
                    doc_uuid = childdoc['document_uuid_s']
                    study_id= childdoc['id']
                    upValue=np.nan
                    loValue=np.nan
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
                    effectendpoint_synonym_ss=[]
                    uncertainty=np.nan
                    uncertainty_type=''
                    
                    textValue=''
                                        
 
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
                        assay_uuid_s = childdoc['assay_uuid_s']
                    except :
                        assay_uuid_s = document_uuid
                        
                    try:
                        investigation_uuid_s = childdoc['investigation_uuid_s']
                    except :
                        investigation_uuid_s = assay_uuid_s                        


                    try:
                        reference = childdoc['reference_s']
                    except :
                        pass 

                    try:
                        reference_year = childdoc['reference_year_s']
                    except :
                        pass 

                    try:
                        reference_owner = childdoc['reference_owner_s']
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
                        effectendpoint_synonym_ss = childdoc['effectendpoint_synonym_ss']
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

                    try:
                        upValue = childdoc['upValue_d']
                    except :
                        pass
                        
                    try:
                        uncertainty = childdoc['err_d']
                    except :
                        pass    
                    try:
                        uncertainty_type = childdoc['errQualifier_s']
                    except :
                        uncertainty_type=""                                                
                        
                    try:
                        textValue = childdoc['textValue_s']
                        #print(json.dumps(childdoc, indent=2))

                    except :
                        textValue=""                        

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
                    if (unit is None or unit=='') and (not np.isnan(loValue) or not np.isnan(upValue)):
                        quality_remark.append("Missing unit")
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
                        quality_remark.append('empty endpoint')

                    substance_uuid = doc['s_uuid_hs']

                    substancetype = None
                    try:
                        substancetype=doc['substanceType_hs']
                    except:
                        substancetype = None

                         
                    row={
                         'db' : ''.join(doc['dbtag_hss']),
                         'm.substance.name' : doc['name_hs'], 
                         'm.public.name' : doc['publicname_hs'], 
                         'm.materialprovider' : doc['owner_name_hs'], 
                         #'substance.uuid' : substance_uuid, 
                         'm.substance.type' : substancetype, 
                         'p.oht.module' : childdoc['topcategory_s'],
                         'p.oht.section' : childdoc['endpointcategory_s'],
                         'p.guidance' : guidance,
                         'p.reference' : reference,                         
                         'p.reference_year' : reference_year,           
                         'p.study_provider' : reference_owner,                                    
                         'value.endpoint' : effectendpoint,
                         'value.endpoint_synonym' : ';'.join(effectendpoint_synonym_ss),                         
                         'value.endpoint_type' : effectendpoint_type,
                         'value.range.lo.qualifier' : loQualifier,
                         'value.range.up.qualifier' : upQualifier,
                         'value.range.lo' : loValue,
                         'value.range.up' : upValue,
                         'value.unit' : unit,
                         'value.text' : textValue,
                         'value.uncertainty' : uncertainty,
                         'value.uncertainty_type' : uncertainty_type,

                         'xR.reliability' : reliability,
                         #'x.params.test_organism' : test_organism,
                         #'Exposure_d' : exposure_d,
                         #'Exposure_h' : exposure_h,
                         'xR.studyResultType' : studyResultType,
                         'xR.purposeFlag' : purposeFlag,
                         'xx.QualityRemark' : ';'.join(quality_remark),
                         'uuid.substance' : s_uuid,                         
                         'uuid.document' : document_uuid,
                         'uuid.assay' : assay_uuid_s,
                         'uuid.investigation' : investigation_uuid_s,
                         

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
                        fields = self.settings["fields"]["conditions"]
                        for field in fields:
                            key="x.conditions." + field.replace("_s", "")
                            value = conditions[study_id][field]
                            if pd.isna(value):
                                value=np.nan
                            row[key] = value
                    except:
                        pass

                    try:
                        fields = self.settings["fields"]["params"]
                        for field in fields:
                            key="x.params."+field.replace("_s", "")
                            value = params[doc_uuid][field]
                            if pd.isna(value):
                                value=np.nan
                            row[key] = value
                    except :
                        pass 

                    for key,value in cas.items():
                        row['c.CAS']=key
                    for key,value in einecs.items():
                        row['c.EINECS']=key    


                    rows.append(row)    
        return (rows)
    

class Materials:
    def getQuery(self,query='*:*',facets=None,fq='', fl='*',rows=1000):
        query={'q': query,'fq' : fq, "wt" : "json", 'fl' : fl, 'rows': rows}
        return query
         

     