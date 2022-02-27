# curation

## Setup development environment

```sh
# configure dev environment
ploomber install


# ...or use venv directly (choose a path-to-venv)
python -m venv {path-to-venv}

# activate environment (unix)
source {path-to-venv}/bin/activate
# activate environment (windows cmd.exe)
{path-to-venv}\Scripts\activate.bat
# activate environment (windows PowerShell)
{path-to-venv}\Scripts\Activate.ps1

# the install dependencies
pip install --requirement requirements.txt
```


Create `env.yaml` in `pipelines/curation` folder. 
API endpoints and plans are at https://api.ideaconsult.net

```
folder_output: "/results"
solr_api_url: "https://api.ideaconsult.net/nanoreg1"
solr_api_key: ""
templates_pchem: "https://search.data.enanomapper.net/api/templates/pchem.json"
```


## Running the pipeline

```sh
ploomber build

# start an interactive session
ploomber interact
```

## Exporting to other systems

[soopervisor](https://soopervisor.readthedocs.io/) allows you to run ploomber projects in other environments (Kubernetes, AWS Batch, AWS Lambda and Airflow). Check out the docs to learn more.


## Conda environment
conda env export -n ml2 > environment.yml

#conda env update -f environment.yml -n ml3

#https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#building-identical-conda-environments
conda list --explicit

#conda create --name ml4 --clone ml_template

conda create -n pipeline1 pytorch torchvision cudatoolkit spacy cupy  ploomber

conda update -n base -c defaults 

Note: scispacy requires older spacy version 
workaround - first  conda install nmslib  ; then pip instal scispacy

----------
This project has received funding from the European Union's Horizon 2020 research and innovation programme under grant agreement 814426 NanoinformaTIX
