# + tags=["parameters"]
upstream = None
solr_url = None
solr_user = None
solr_pass = None
product = None
# -

from pynanomapper import client_solr
from pynanomapper import annotation
from requests.auth import HTTPBasicAuth
import json
import zlib

facets = client_solr.Facets()
#facets.set_annotation_folder("../../annotation")

df = facets.summary(solr_url,HTTPBasicAuth(solr_user, solr_pass), query="type_s:study",
            fields=["owner_name_s","substanceType_s","publicname_s","topcategory_s","endpointcategory_s","E.method_s","E.method_synonym_ss","E.animal_model_s","E.cell_type_s","effectendpoint_s","effectendpoint_synonym_ss",
                            "E.exposure_route_s","_CONDITION_exposure_time_d","_CONDITION_exposure_time_UNIT_s"])              
df.rename(columns={"Number of data points": "number_of_points_d"},inplace=True)
df["type_s"] = "metadata"

from measurement.utils import guess
def time_format(x):
    value = x['_CONDITION_exposure_time_d']
    unit = x['_CONDITION_exposure_time_UNIT_s']
    if unit=="_":
        return None
    try:
        if unit.strip()=="h":
            unit="hour"
        elif unit=="min after administration":
            unit="min"
        elif unit=="mont hs":
            unit = "day"
            value = 30*value
        elif unit=="week":
            unit= "day"
            value = 7* value
        elif unit=="d":
            unit="day"
        msmt = guess(value,unit)
        return msmt.min
    except Exception as err:
        print("{} {} {}".format(value,unit,err))
        return None

try:
    df["E.exposure_time_min_d"] = df.apply(lambda x:time_format(x),axis=1)
except:
    pass

df["E.exposure_time_min_d"].unique()
df.drop(columns=['_CONDITION_exposure_time_d','_CONDITION_exposure_time_UNIT_s','substanceType_name','endpointcategory_term','endpointcategory_name'],inplace=True)

#f = lambda x: None if x=='_' else x
#for col in df.columns:
#    df[col] = df[col].map(f)
    #print(col,df[col].unique())
df.dropna(axis=1,how="all",inplace=True)    


df.head()


with open(product["data"], 'w') as outfile:
    outfile.write(df.to_json(orient = 'records',indent=2))