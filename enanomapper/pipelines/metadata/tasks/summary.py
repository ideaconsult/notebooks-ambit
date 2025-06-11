import pandas as pd
import json


# + tags=["parameters"]
upstream = ["facets"]
product = None
# -

df = pd.read_json(upstream["facets"]["data"])
df.head()

group_cols = ["owner_name_s"]
result = df.groupby(group_cols)['number_of_points_d'].sum().reset_index()
result.to_excel(product["data"])