# + tags=["parameters"]
upstream = ["onto"]
folder_output = None
model_embedding = None
hnsw_distance = None
# -

import os,os.path
import pandas as pd

ann_hits = os.path.join(folder_output,"terms","{}_{}_params_hits.txt".format(model_embedding,hnsw_distance))
df = pd.read_csv(ann_hits,sep="\t")

import plotly.express as px
tmp = df[["distance","rank"]].dropna()
fig = px.histogram(tmp, x="distance",histnorm='probability density',
    title="{} {}".format(model_embedding,hnsw_distance),color="rank")
fig.show()

tmp = df[["distance","rank","query"]].dropna()
#.loc[df["rank"]==1].dropna()
tmp=tmp.sort_values(by="distance")
fig = px.histogram(tmp, x="query",y="distance",histfunc='avg',
    title="{} {}".format(model_embedding,hnsw_distance),color="rank")
fig.show()