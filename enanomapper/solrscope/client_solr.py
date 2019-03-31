import requests
import pandas as pd

from pandas.io.json import json_normalize

       
def post(service_uri,query,auth=None):
    r = requests.post(service_uri + "/select",data=query, auth=auth)
    return r


    
class Facets:

    def getQuery(self,query='*:*',facets=["endpointcategory_s","effectendpoint_s","unit_s"],fq=''):
        json_facet = self.getNestedFacets(facets);
        query={'q': query,'fq' : fq, "wt" : "json", "json.facet": json_facet, 'rows': 0}
        return query

    def parse(self,facets,key="ALL",prefix="",process=None):
        count = facets['count']
        if 'val' in facets:
            val = facets['val']            
        else:
            val='ALL'
        if process is None:    
            print("{}'{}'\t{}".format(prefix,val,count)) 
        else:
            process(prefix,val,count,key)
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
                    self.parse(bucket,key,prefix+"\t")

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

def getSolrQuery(settings,service_url=None):
    
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
        'url': service_url,
        'fl' : fl,
    #    'fl' : 'name_hs,substanceType_hs,s_uuid_hs,[child parentFilter=filter(type_s:substance) childFilter="filter(type_s:study AND '+ settings['studyfilter']  +') OR filter(type_s:composition AND component_s:CONSTITUENT) OR filter(type_s:PARAMS AND '+settings['studyfilter']+') OR filter(type_s:CONDITIONS AND '+settings['studyfilter']+' limit 100000)"]',    
         #'fq' :'substanceType_hs:(MONO CONSTITUENT SUBSTANCE)',
         'fq' : '',
         'q' : '{!parent which=type_s:substance}'
    }


