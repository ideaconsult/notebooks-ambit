# + tags=["parameters"]
upstream = ["retrieve"]
folder_output = None
# -


import os,os.path
import pandas as pd


params = pd.read_csv(os.path.join(folder_output,"params.txt"),sep="\t",encoding="utf-8")

from thefuzz import process

prms =params["field_clean"].unique()
tmp = []
for prm in prms:
    _m = process.extract(prm, prms, limit=5)
    for m in _m:
        tmp.append([prm,m[0],m[1]])
    
df = pd.DataFrame(tmp,columns=["field_clean","match","score"])
df.to_csv(os.path.join(folder_output,"terms","matched_params.txt"),sep="\t",index=False)    