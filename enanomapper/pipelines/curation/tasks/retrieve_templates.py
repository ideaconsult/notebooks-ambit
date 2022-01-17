# + tags=["parameters"]
upstream = None
templates_pchem = None
folder_output = None
# -

import requests
import json
import os,os.path

try:
    results = requests.get(templates_pchem)

    with open(os.path.join(folder_output,"templates","pchem.json"), 'w',encoding="utf-8") as outfile:
        json.dump(results.json(), outfile)
except Exception as err:
    print(err)