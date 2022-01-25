# + tags=["parameters"]
upstream = None
folder_output = None
blueprint = None
# -

import os,os.path
import json
import urllib.parse

def convert_blueprint(file):
    project="GRACIOUS"
    tagger = []
    with open(file,encoding="utf-8-sig") as json_file:
        df = json.load(json_file)

    kb = {}
    classes = {}
    for k in df["knowledgebases"]:
        
        try:
            kb[k["name"]] = k["enumerations"]
            print(k["name"])
            try:
                classes[k["name"]] = k["classes"]
            except:
                pass
        except Exception as err:
            print("{} error reading `{}'".format(k["name"],err)) 
    load_endpoints(kb,tagger,project)  
    load_methods(kb,tagger,project)   
    h = classes["IATA_KB"]        
    parse_grouping_kb(tagger,h,project)     
    return tagger


def load_endpoints(kb,tagger,project):

    endpoints = kb["ENDPOINT_KB"]
    prefix = "https://graciouswiki.greendecision.eu/ENDPOINT_KB/"
    for level1 in endpoints:
        
        dictname="GRACIOUS_ENDPOINT_LEVEL1"
        
        _id = level1['name']
        _name = _id.replace("PC_","").replace("_"," ").lower()
            
        try:
                
            tagger.append({"id" : _id, "name" : [_id,_name],  'definition' : [level1['note']], "ontology" : [project,dictname], "prefix": prefix,  "parents" : ["GRACIOUS_KB"]})
            for level2 in level1["enumerates"]:
                url = prefix+urllib.parse.quote(level1['name'])
                dictname="GRACIOUS_ENDPOINT_LEVEL2"
                _id = level2['name']
                _name = _id.replace("EP_","").replace("_"," ").lower()
                item = {"id" : _id,"name" : [_id,_name],  'definition' : [], "ontology" : [project,dictname], "parents" : [url], "prefix" :[url]}
                tagger.append(item)
                try:
                    _note = ''
                    if isinstance(level2['note'], str):
                        item['definition'] = level2['note']
                    else:    
                        item['definition'] = level2['note']['definition']['text']
                        item['ontology'].append(level2['note']['definition']['source'])
                
                except Exception as err: 
                    pass
        except Exception as err:
            print(">> {}\t{}".format(err,_name))

def load_methods(kb,tagger,project):
    guidelines = kb["GUIDELINES_METHODS_KB"]

    prefix = "https://graciouswiki.greendecision.eu/GUIDELINES_METHODS_KB/"
    #print(guidelines)
    for level1 in guidelines:
        
        dictname="GRACIOUS_ORGS"
        item = {"id" : level1['name'],"name" : [level1['name']],  'definition' : [], "ontology" : [project,dictname], "prefix": [prefix], "parents" : ["GRACIOUS_KB"]}
        tagger.append(item);    
        try:
            item['definition'] = [level1['note']]
        except Exception as err: 
            pass
        
        for level2 in level1["enumerates"]:
            dictname="GRACIOUS_GUIDELINES"
            url = prefix+urllib.parse.quote(level1['name'])
            try:
                item = {"id" : level2['name'], "name" : [level2['name']], 'definition' : [], "ontology" : [project,dictname], "parents" : [url], "prefix" : [url]}
                tagger.append(item)
            except Exception as err: 
                print(err)
            try:
                item['definition'] = [level2['note']]
            except Exception as err: 
                pass       

def parse_grouping_kb(tagger,classes,project="GRACIOUS"):
    for h in classes:
        _id = h["class"].strip("'")
        item = {"id": _id, "name" : [_id]}
        if 'note' in h:
            item["definition"] = [h["note"]]
        if 'kindof' in h:
            item["parents"] = [h['kindof']]
        item["ontology"] = [project,"IATA_KB"]
        tagger.append(item)            
        if 'decendents' in h:
            parse_grouping_kb(tagger,h['decendents'])

if os.path.isfile(blueprint):
    tagger = convert_blueprint(blueprint)
    print(tagger)
    outfile = os.path.join(folder_output,"terms","blueprint.json")
    with open(outfile, "w") as write_file:
        json.dump(tagger, write_file)