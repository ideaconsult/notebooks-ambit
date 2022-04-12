# + tags=["parameters"]
upstream = ["retrieve_templates"]
templates_pchem = None
folder_output = None
# -

import pandas as pd 
import glob
import os.path
folder = "tbd"


def column(num, res = ''):
       return column((num - 1) // 26, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[(num - 1) % 26] + res) if num > 0 else res


files = glob.glob(os.path.join(folder,"*.xlsx"), recursive=True)
for file in files:
    params = { }
    df = pd.read_excel(file, None);
    for sheet in df.keys():
        print(sheet)
        df_sheet = pd.read_excel(file,sheet_name=sheet,header=None)
        try:
            cols = df_sheet.iloc[1]
            c = 0
            for col in cols:
                c = c+1
                params[col] =  {
					"COLUMN_INDEX": column(c)
				}
        except Exception as err:
            pass
    print(params)
#front_sheet = pd.read_excel(file_metadata,sheet_name="Front sheet",header=None)