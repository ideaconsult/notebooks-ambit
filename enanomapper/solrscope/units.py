#units conversion
#http://python-measurement.readthedocs.io/en/latest/topics/measures.html
#pip install measurement
from measurement.measures import Weight
from measurement.measures import Volume
from measurement.measures import Time
from measurement.measures import Distance

from measurement.base import MeasureBase
from measurement.base import BidimensionalMeasure

from measurement.utils import guess
from os.path import isfile, join
import json

def convert_units(value,from_units, to_units="nm",measures=None,debug=False):
    try:
        to_units = to_units.replace("\u00b5","u")
        from_units = from_units.replace("\u00b5","u")
        m = guess(value, from_units)
        xp='m.' + to_units
        return (eval(xp))
    except Exception as err:
        if debug:
            print(value,from_units,to_units)
            print(err)
        return None
    
Distance.ALIAS['\u00B5m'] = 'um'

class Dose(BidimensionalMeasure):
    PRIMARY_DIMENSION = Volume
    REFERENCE_DIMENSION = Weight

    ALIAS = {
        'l/kg' : 'l__kg'
    }
    
class Percent(MeasureBase):
    STANDARD_UNIT = 'percent'
    UNITS = {
        'percent': 1.0
    }
    ALIAS = {
        '\u0025' : 'percent',
        '%DNA IN TAIL'  : 'percent',
        '% DNA in Tail' : 'percent',
        '%DNA in Tail'  : 'percent',
        '% DNA IN TAIL' : 'percent'
    }
    SI_UNITS = ['percent']
    
class Molar(MeasureBase):
    STANDARD_UNIT = 'mol'
    UNITS = {
        'mol': 1.0,
        '\u00B5mol' : 1e-6,
        'umol' : 1e-6,
        'mmol' : 1e-3,
    }
    ALIAS = {
        'micromol': 'umol',
        'millimol': 'mmol'
    }
    SI_UNITS = ['mol']

class Concentration(BidimensionalMeasure):
    PRIMARY_DIMENSION = Weight
    REFERENCE_DIMENSION = Volume

    ALIAS = {
        'mg/l' : 'mg__l',
        'ug/l' : 'ug__l',
        'g/l': 'g__l',
        '\u00B5g/l' : 'ug__l',
        '\u00B5g/ml' : 'ug__ml',
        'microgram/l': 'ug__l',
        'micrograms per ml' : 'ug__ml',
        'milligram per l' : 'mg__l', 
        'milligram / l' : 'mg__l',
        'micrograms per mL' : 'ug__ml'
    }
    
  
    
class ConcentrationMolar(BidimensionalMeasure):
    PRIMARY_DIMENSION = Molar
    REFERENCE_DIMENSION = Volume

    ALIAS = {
        'mmol/l' : 'mmol__l',
        'umol/l' : 'umol__l',
        'mol/l': 'mol__l',
        '\u00B5mol/l' : 'umol__l',
        '\u00B5mol/ml' : 'umol__ml',
        'micromol/l': 'umol__l',
        'micromol per ml' : 'umol__l',
        'millimol per l' : 'mmol__l', 
        'millimol / l' : 'mmol__l',
        'micromol per mL' : 'umol__ml'
    }    
    
     

def unitsdict(mypath,df):
    unit_dict={}
    file_ud=join(mypath,'unitdict.json')
    if isfile(file_ud):
        json_data=open(file_ud).read()
        unit_dict = json.loads(json_data)  

    for unit in df.unit.unique():
        if not unit in unit_dict:
            unit_dict[unit]= unit
        print('{:s}\t{:s}'.format(unit,unit_dict[unit]))        
    with open(file_ud, 'w') as fp:
        json.dump(unit_dict, fp, indent=2)
    return unit_dict