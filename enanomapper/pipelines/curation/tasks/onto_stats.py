# + tags=["parameters"]
upstream = ["onto"]
folder_output = None
model_embedding = None
hnsw_distance = None
ann_param_hits = None
# -

import os,os.path
import pandas as pd

df = pd.read_csv(ann_param_hits,sep="\t")

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