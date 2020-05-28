
# Retrieve data from eNanomapper database
https://search.data.enanomapper.net/

- This notebook uses Apache Solr API and AMBIT REST API  
- see OpenAPI3 interactive documentation at https://api.ideaconsult.net


```python
from importlib import reload 
import yaml
from pynanomapper import aa
from pynanomapper import units
import ipywidgets as widgets
from ipywidgets import interact, interactive, fixed, interact_manual
import requests

import measurement
from pynanomapper import client_solr
from pynanomapper import client_ambit
from pynanomapper import annotation

import pandas as pd
import os.path
import numpy as np
import datetime, time
import json
import sys
import ipywidgets as widgets

import logging
from logging.config import fileConfig
fileConfig('logging_endpoints_config.ini')

global logger
logger = logging.getLogger()

logger.debug('Started at %s \t%s',os.name, datetime.datetime.now())
import warnings
warnings.simplefilter("ignore")

```

### Retrieve endpoints 


```python
print('Select enanoMapper aggregated search service:')
style = {'description_width': 'initial'}
config,config_servers, config_security, auth_object, msg = aa.parseOpenAPI3()    
service_widget = widgets.Dropdown(
    options=config_servers['url'],
    description='Service:',
    disabled=False,
    style=style
)
if config_security is None:
    service = interactive(aa.search_service_open,url=service_widget)
else:
    print(msg)
    apikey_widget=widgets.Text(
            placeholder='',
            description=config_security,
            disabled=False,
            style=style
    )    
    service = interactive(aa.search_service_protected,url=service_widget,apikey=apikey_widget)    

display(service)
```

    Select enanoMapper aggregated search service:
    Enter `X-Gravitee-Api-Key` you have received upon subscription to http://api.ideaconsult.net
    


    interactive(children=(Dropdown(description='Service:', options=('https://api.ideaconsult.net/enanomapper', 'ht…



```python
service_uri=service_widget.value
if auth_object!=None:
    auth_object.setKey(apikey_widget.value)
print("Sending queries to {}".format(service_uri))

```

    Sending queries to https://api.ideaconsult.net/nanoreg1
    


```python
facets = client_solr.Facets()

df = facets.summary(service_uri,auth_object, query="*:*",fields=["topcategory_s","endpointcategory_s"])    
df.head()

```




<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>topcategory_s</th>
      <th>endpointcategory_s</th>
      <th>Number of data points</th>
      <th>endpointcategory_term</th>
      <th>endpointcategory_name</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>TOX</td>
      <td>ENM_0000068_SECTION</td>
      <td>10990</td>
      <td>http://www.bioassayontology.org/bao#ENM_0000068</td>
      <td>CellViability</td>
    </tr>
    <tr>
      <th>1</th>
      <td>TOX</td>
      <td>TO_GENETIC_IN_VITRO_SECTION</td>
      <td>7811</td>
      <td>http://www.bioassayontology.org/bao#BAO_0002167</td>
      <td>Genetic toxicity invitro</td>
    </tr>
    <tr>
      <th>2</th>
      <td>TOX</td>
      <td>NPO_1339_SECTION</td>
      <td>3429</td>
      <td>http://purl.obolibrary.org/obo/NPO_1339</td>
      <td>Immunotoxicity</td>
    </tr>
    <tr>
      <th>3</th>
      <td>TOX</td>
      <td>TO_REPEATED_ORAL_SECTION</td>
      <td>1487</td>
      <td>http://purl.enanomapper.org/onto/ENM_0000021</td>
      <td>Repeated dose toxicity-oral</td>
    </tr>
    <tr>
      <th>4</th>
      <td>TOX</td>
      <td>ENM_0000044_SECTION</td>
      <td>1322</td>
      <td>http://purl.enanomapper.org/onto/ENM_0000044</td>
      <td>Barrier integrity</td>
    </tr>
  </tbody>
</table>
</div>




```python
top_widget = widgets.Dropdown(
    options=df['topcategory_s'].unique(),
    value="P-CHEM",
    description='Select:',
    disabled=False,
)
category_widget = widgets.Dropdown(
    options=list(df[df['topcategory_s']=="P-CHEM"][["endpointcategory_name","endpointcategory_s"]].itertuples(index=False,name=None)),
    #value=,
    description='Category:',
    disabled=False,
)
freetext_widget=widgets.Text(
    value='NM220,NM101',
    description='Free text query',
    disabled=False
)
endpoint_widget=widgets.Text(
    value='*',
    description='Endpoint',
    disabled=False
)
def define_query(_top,_section,_freetext,_endpoint):
    #category_widget.options=df[df['topcategory_s']==top]['endpointcategory_s'].unique()
    filtered = df[df['topcategory_s']==_top]
    category_widget.options = list(filtered[["endpointcategory_name","endpointcategory_s"]].itertuples(index=False,name=None))
    top = _top
    section= _section
    
    
interact(define_query,_top= top_widget,_section=category_widget,_freetext=freetext_widget,_endpoint=endpoint_widget)
```


    interactive(children=(Dropdown(description='Select:', index=1, options=('TOX', 'P-CHEM', 'ECOTOX'), value='P-C…





    <function __main__.define_query(_top, _section, _freetext, _endpoint)>



#### Setup the query


```python
top = top_widget.value
section = category_widget.value
materialfilter=freetext_widget.value
endpoint=endpoint_widget.value
if "" == materialfilter:
    materialfilter=None
logger.info('{}\t{}\t{}\t{}'.format(top,section,materialfilter,endpoint))

docs_query = client_solr.StudyDocuments()
docs_query.settings['endpointfilter'] = ' effectendpoint_s: {}'.format(endpoint)
docs_query.settings['query_guidance'] = None
docs_query.settings['query_organism'] = None
docs_query.settings['fields'] = None
docs_query.setStudyFilter({' topcategory_s': top, 'endpointcategory_s':section}) 
                    
query = docs_query.getQuery(textfilter=materialfilter,facets=None,fq=None, rows=10, _params=True, _conditions=True, _composition=False );
logger.info(query)
```

    2019-12-15 10:30:48,787  INFO     P-CHEM	ZETA_POTENTIAL_SECTION	NM220,NM101	*
    2019-12-15 10:30:48,787  INFO     {'q': '{!parent which=type_s:substance}(NM220,NM101)', 'fq': None, 'wt': 'json', 'fl': 'dbtag_hss,name_hs,publicname_hs,substanceType_hs,owner_name_hs,s_uuid_hs,[child parentFilter=filter(type_s:substance) childFilter="filter(type_s:study AND     topcategory_s:P-CHEM AND endpointcategory_s:ZETA_POTENTIAL_SECTION AND  effectendpoint_s: *)  OR filter(type_s:params AND     topcategory_s:P-CHEM AND endpointcategory_s:ZETA_POTENTIAL_SECTION)  OR filter(type_s:conditions AND     topcategory_s:P-CHEM AND endpointcategory_s:ZETA_POTENTIAL_SECTION) " limit=10000]', 'json.facet': '', 'rows': 10}
    

### Run the query


```python
r = client_solr.get(service_uri,query=query,auth=auth_object)
logger.info(r.status_code)
docs=r.json()['response']['docs']
#print(docs)
rows = docs_query.parse(docs)


```

    2019-12-15 10:30:51,891  INFO     200
    2019-12-15 10:30:51,893  INFO     {
      "dbtag_hss": [
        "NNRG"
      ],
      "name_hs": "NM-100 (TiO2 50-150 nm)",
      "publicname_hs": "JRCNM01000a",
      "owner_name_hs": "NANoREG",
      "substanceType_hs": "NPO_1486",
      "s_uuid_hs": "NNRG-18280a4a-45e9-adc0-df3b-125397b1255f"
    }
    


```python
#print("Substances: {}".format(len(rows)))
results = pd.DataFrame(rows)
results.to_csv(section+".nosmiles.txt",sep='\t',index=False)
#df.head()
results.head()
```




<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>db</th>
      <th>m.materialprovider</th>
      <th>m.public.name</th>
      <th>m.substance.name</th>
      <th>m.substance.type</th>
      <th>p.guidance</th>
      <th>p.oht.module</th>
      <th>p.oht.section</th>
      <th>p.reference</th>
      <th>p.reference_year</th>
      <th>...</th>
      <th>x.params.MEDIUM.ph_d</th>
      <th>x.params.MEDIUM.temperature_UNIT</th>
      <th>x.params.MEDIUM.temperature_d</th>
      <th>x.params.T.PDI</th>
      <th>x.params.Vial</th>
      <th>x.params.guidance</th>
      <th>xR.purposeFlag</th>
      <th>xR.reliability</th>
      <th>xR.studyResultType</th>
      <th>xx.QualityRemark</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>NNRG</td>
      <td>NANoREG</td>
      <td>JRCNM01001a</td>
      <td>NM-101 (TiO2 6 nm)</td>
      <td>NPO_1486</td>
      <td>DLS</td>
      <td>P-CHEM</td>
      <td>ZETA_POTENTIAL_SECTION</td>
      <td>IEM_NM101_MEM_25ug/ml_1h_zeta</td>
      <td>2016</td>
      <td>...</td>
      <td>NaN</td>
      <td>Celsius</td>
      <td>37.0</td>
      <td>NaN</td>
      <td>990472</td>
      <td>DLS</td>
      <td></td>
      <td>None</td>
      <td>Measured</td>
      <td></td>
    </tr>
    <tr>
      <th>1</th>
      <td>NNRG</td>
      <td>NANoREG</td>
      <td>JRCNM01001a</td>
      <td>NM-101 (TiO2 6 nm)</td>
      <td>NPO_1486</td>
      <td>DLS</td>
      <td>P-CHEM</td>
      <td>ZETA_POTENTIAL_SECTION</td>
      <td>IEM_NM101_MEM_25ug/ml_24h_zeta</td>
      <td>2016</td>
      <td>...</td>
      <td>NaN</td>
      <td>Celsius</td>
      <td>37.0</td>
      <td>NaN</td>
      <td>990472</td>
      <td>DLS</td>
      <td></td>
      <td>None</td>
      <td>Measured</td>
      <td></td>
    </tr>
    <tr>
      <th>2</th>
      <td>NNRG</td>
      <td>NANoREG</td>
      <td>JRCNM01001a</td>
      <td>NM-101 (TiO2 6 nm)</td>
      <td>NPO_1486</td>
      <td>DLS</td>
      <td>P-CHEM</td>
      <td>ZETA_POTENTIAL_SECTION</td>
      <td>IEM_NM101_RPMI_25ug/ml_1h_zeta</td>
      <td>2016</td>
      <td>...</td>
      <td>NaN</td>
      <td>Celsius</td>
      <td>37.0</td>
      <td>NaN</td>
      <td>990472</td>
      <td>DLS</td>
      <td></td>
      <td>None</td>
      <td>Measured</td>
      <td></td>
    </tr>
    <tr>
      <th>3</th>
      <td>NNRG</td>
      <td>NANoREG</td>
      <td>JRCNM01001a</td>
      <td>NM-101 (TiO2 6 nm)</td>
      <td>NPO_1486</td>
      <td>DLS</td>
      <td>P-CHEM</td>
      <td>ZETA_POTENTIAL_SECTION</td>
      <td>IEM_NM101_RPMI_25ug/ml_24h_zeta</td>
      <td>2016</td>
      <td>...</td>
      <td>NaN</td>
      <td>Celsius</td>
      <td>37.0</td>
      <td>NaN</td>
      <td>990472</td>
      <td>DLS</td>
      <td></td>
      <td>None</td>
      <td>Measured</td>
      <td></td>
    </tr>
    <tr>
      <th>4</th>
      <td>NNRG</td>
      <td>NANoREG</td>
      <td>JRCNM01000a</td>
      <td>NM-100 (TiO2 110 nm)</td>
      <td>NPO_1486</td>
      <td>DLS</td>
      <td>P-CHEM</td>
      <td>ZETA_POTENTIAL_SECTION</td>
      <td>IEM_NM100_MEM_25ug/ml_1h_zeta</td>
      <td>2016</td>
      <td>...</td>
      <td>NaN</td>
      <td>Celsius</td>
      <td>37.0</td>
      <td>NaN</td>
      <td>06978</td>
      <td>DLS</td>
      <td></td>
      <td>None</td>
      <td>Measured</td>
      <td></td>
    </tr>
  </tbody>
</table>
<p>5 rows × 49 columns</p>
</div>




```python
results.columns
```




    Index(['db', 'm.materialprovider', 'm.public.name', 'm.substance.name',
           'm.substance.type', 'p.guidance', 'p.oht.module', 'p.oht.section',
           'p.reference', 'p.reference_year', 'p.study_provider', 'uuid.assay',
           'uuid.document', 'uuid.investigation', 'uuid.substance',
           'value.endpoint', 'value.endpoint_synonym', 'value.endpoint_type',
           'value.range.lo', 'value.range.lo.qualifier', 'value.range.up',
           'value.range.up.qualifier', 'value.text', 'value.uncertainty',
           'value.uncertainty_type', 'value.unit', 'x.params.Dispersion protocol',
           'x.params.MEDIUM', 'x.params.MEDIUM.CO2_concentration_UNIT',
           'x.params.MEDIUM.CO2_concentration_d',
           'x.params.MEDIUM.O2_concentration_UNIT',
           'x.params.MEDIUM.O2_concentration_d', 'x.params.MEDIUM.composition',
           'x.params.MEDIUM.ionictrength_UNIT', 'x.params.MEDIUM.ionictrength_d',
           'x.params.MEDIUM.ph_LOQUALIFIER', 'x.params.MEDIUM.ph_LOVALUE_d',
           'x.params.MEDIUM.ph_UPQUALIFIER', 'x.params.MEDIUM.ph_UPVALUE_d',
           'x.params.MEDIUM.ph_d', 'x.params.MEDIUM.temperature_UNIT',
           'x.params.MEDIUM.temperature_d', 'x.params.T.PDI', 'x.params.Vial',
           'x.params.guidance', 'xR.purposeFlag', 'xR.reliability',
           'xR.studyResultType', 'xx.QualityRemark'],
          dtype='object')




```python
import numpy as np
def highlight_max(s):
    is_max = s == s.max()
    return ['background-color: red' if v else '' for v in is_max]

for criteria in ["value.range.lo"]:
    tmp = pd.pivot_table(results, values=criteria, index=['m.public.name'], columns=['p.oht.module','p.oht.section','p.guidance','value.endpoint','value.endpoint_type','value.range.lo.qualifier','value.unit'], aggfunc=np.mean).reset_index()
    #tmp.style.highlight_null(null_color='red')
    
    #display(tmp.style.apply(highlight_max,subset=top_sections))
    display(tmp.style.apply(highlight_max))
```


<style  type="text/css" >
    #T_36d424be_1f15_11ea_a414_80ee7350bfa7row0_col2 {
            background-color:  red;
        }    #T_36d424be_1f15_11ea_a414_80ee7350bfa7row1_col1 {
            background-color:  red;
        }    #T_36d424be_1f15_11ea_a414_80ee7350bfa7row2_col0 {
            background-color:  red;
        }</style>  
<table id="T_36d424be_1f15_11ea_a414_80ee7350bfa7" > 
<thead>    <tr> 
        <th class="index_name level0" >p.oht.module</th> 
        <th class="col_heading level0 col0" >m.public.name</th> 
        <th class="col_heading level0 col1" colspan=2>P-CHEM</th> 
    </tr>    <tr> 
        <th class="index_name level1" >p.oht.section</th> 
        <th class="col_heading level1 col0" ></th> 
        <th class="col_heading level1 col1" colspan=2>ZETA_POTENTIAL_SECTION</th> 
    </tr>    <tr> 
        <th class="index_name level2" >p.guidance</th> 
        <th class="col_heading level2 col0" ></th> 
        <th class="col_heading level2 col1" colspan=2>DLS</th> 
    </tr>    <tr> 
        <th class="index_name level3" >value.endpoint</th> 
        <th class="col_heading level3 col0" ></th> 
        <th class="col_heading level3 col1" colspan=2>ZETA POTENTIAL</th> 
    </tr>    <tr> 
        <th class="index_name level4" >value.endpoint_type</th> 
        <th class="col_heading level4 col0" ></th> 
        <th class="col_heading level4 col1" colspan=2></th> 
    </tr>    <tr> 
        <th class="index_name level5" >value.range.lo.qualifier</th> 
        <th class="col_heading level5 col0" ></th> 
        <th class="col_heading level5 col1" colspan=2></th> 
    </tr>    <tr> 
        <th class="index_name level6" >value.unit</th> 
        <th class="col_heading level6 col0" ></th> 
        <th class="col_heading level6 col1" ></th> 
        <th class="col_heading level6 col2" >mV</th> 
    </tr></thead> 
<tbody>    <tr> 
        <th id="T_36d424be_1f15_11ea_a414_80ee7350bfa7level0_row0" class="row_heading level0 row0" >0</th> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row0_col0" class="data row0 col0" >JRCNM01000a</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row0_col1" class="data row0 col1" >nan</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row0_col2" class="data row0 col2" >-11.3928</td> 
    </tr>    <tr> 
        <th id="T_36d424be_1f15_11ea_a414_80ee7350bfa7level0_row1" class="row_heading level0 row1" >1</th> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row1_col0" class="data row1 col0" >JRCNM01001a</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row1_col1" class="data row1 col1" >-23.45</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row1_col2" class="data row1 col2" >-12.4036</td> 
    </tr>    <tr> 
        <th id="T_36d424be_1f15_11ea_a414_80ee7350bfa7level0_row2" class="row_heading level0 row2" >2</th> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row2_col0" class="data row2 col0" >NM-220</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row2_col1" class="data row2 col1" >nan</td> 
        <td id="T_36d424be_1f15_11ea_a414_80ee7350bfa7row2_col2" class="data row2 col2" >-18.4137</td> 
    </tr></tbody> 
</table> 



```python
tmp=results.groupby(by=["m.public.name","p.guidance","value.endpoint","value.endpoint_type","value.range.lo.qualifier","value.unit"]).agg({"value.range.lo" : ["min","max","mean","std","count"]}).reset_index()
tmp.columns = ["_".join(x) for x in tmp.columns.ravel()]
print("Substances {}".format(tmp.shape[0]))
display(tmp)

```

    Substances 4
    


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>m.public.name_</th>
      <th>p.guidance_</th>
      <th>value.endpoint_</th>
      <th>value.endpoint_type_</th>
      <th>value.range.lo.qualifier_</th>
      <th>value.unit_</th>
      <th>value.range.lo_min</th>
      <th>value.range.lo_max</th>
      <th>value.range.lo_mean</th>
      <th>value.range.lo_std</th>
      <th>value.range.lo_count</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>JRCNM01000a</td>
      <td>DLS</td>
      <td>ZETA POTENTIAL</td>
      <td></td>
      <td></td>
      <td>mV</td>
      <td>-16.464</td>
      <td>-2.91</td>
      <td>-11.392833</td>
      <td>6.593190</td>
      <td>6</td>
    </tr>
    <tr>
      <th>1</th>
      <td>JRCNM01001a</td>
      <td>DLS</td>
      <td>ZETA POTENTIAL</td>
      <td></td>
      <td></td>
      <td></td>
      <td>-23.600</td>
      <td>-23.30</td>
      <td>-23.450000</td>
      <td>0.212132</td>
      <td>2</td>
    </tr>
    <tr>
      <th>2</th>
      <td>JRCNM01001a</td>
      <td>DLS</td>
      <td>ZETA POTENTIAL</td>
      <td></td>
      <td></td>
      <td>mV</td>
      <td>-15.627</td>
      <td>-5.90</td>
      <td>-12.403600</td>
      <td>4.091118</td>
      <td>5</td>
    </tr>
    <tr>
      <th>3</th>
      <td>NM-220</td>
      <td>DLS</td>
      <td>ZETA POTENTIAL</td>
      <td></td>
      <td></td>
      <td>mV</td>
      <td>-24.300</td>
      <td>-15.10</td>
      <td>-18.413667</td>
      <td>3.676312</td>
      <td>6</td>
    </tr>
  </tbody>
</table>
</div>


.
