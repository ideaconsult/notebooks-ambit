# + tags=["parameters"]
upstream = ["retrieve","retrieve_templates"]
folder_output = None
# -

import requests
import json
import os,os.path
import pandas as pd

try:
    with open(os.path.join(folder_output,"templates","pchem.json"), 'r',encoding="utf-8") as file:
        template = json.load(file)

    print(template)
except Exception as err:
    print(err)

params = pd.read_csv(os.path.join(folder_output,"params.txt"),sep="\t",encoding="utf-8")

params