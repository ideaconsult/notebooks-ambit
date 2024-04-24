# + tags=["parameters"]
upstream = ["index_sops"]
product = None
dry_run = None
# -

import json
import openai
import time
import re 

def keywords_openai(query,prompt = "extract method and instrument from text. Use  method and instrument as keys in a flat json. Do not use nested json. Do not add other keys. {}",t=0,dry_run=True):
    prompt = prompt.format(query)
    try:
      time.sleep(1)
      if dry_run:
        return query
      response = openai.chat.completions.create(
          messages=[
            {
                "role": "user",
                "content": prompt.format(query),
            },
          ],          
          model="gpt-3.5-turbo-1106",
          response_format={"type": "json_object"},
          temperature=t,
          top_p=1,
          frequency_penalty=0,
          presence_penalty=0
      )
      return response.choices[0]
    except Exception as err:
      print(err)
      return ""


sops = []
with open(upstream["index_sops"]["data"]) as f:
    sops = json.load(f)

n = 0
for sop in sops:
    #if sop["project_s"] in "POLYRISK":
    try:
        print(sop["name_s"])
        txt = sop["_text_"]
        cleaned_text = re.sub(r'[\t\n\s]+', ' ', txt)
        resp = keywords_openai(cleaned_text,dry_run=dry_run)
        _json = json.loads(resp.message.content)
        sop["xai_method"] = _json["method"]
        sop["xai_instrument"] = _json["instrument"]

        with open(product["data"], 'w') as f:
            json.dump(sops, f, indent=4)    
        n = n+1           
    except Exception as err:
       print(err)
    if n>1000:
        break

with open(product["data"], 'w') as f:
    json.dump(sops, f, indent=4)       