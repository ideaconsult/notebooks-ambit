import datetime
import logging

global logger
logger = logging.getLogger()

mypath = './test'

#settings examples
settings = {}
settings['folder'] ='./test'
settings['file']='dataset_FATHEAD_EPA'
settings['query_organism']='Pimephales promelas'
settings['molar'] = True
settings['studyfilter']=' topcategory_s:ECOTOX AND endpointcategory_s:EC_FISHTOX_SECTION AND guidance_s:OECD_TG_203 '
#endpointfilter= ' effectendpoint_s:* '
settings['endpointfilter']= ' effectendpoint_s:LC50 '
#with open(settings['folder']+'settings.json', 'w') as fp:
#    json.dump(settings, fp)
    
#
settings = {}
settings['folder'] ='./test'
settings['file']='dataset_DAPHNIA_EPA'
settings['file']='dataset_DAPHNIA_DEMETRA'
settings['query_organism']="Daphnia magna"  
settings['studyfilter']=' topcategory_s:ECOTOX AND endpointcategory_s:EC_DAPHNIATOX_SECTION AND guidance_s:OECD_TG_202 '
settings['endpointfilter']= ' effectendpoint_s:LC50 '

