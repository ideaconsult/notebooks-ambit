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