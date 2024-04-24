# + tags=["parameters"]
upstream = None
product = None
config_input = None
# -

import os
from glob import glob
import json
from tika import parser
import uuid
import re


# Function to index documents
def index_documents(directory,project, workpackage):
    indexed_documents = []

    # Find all documents in the directory
    document_files = glob(os.path.join(directory, '*.docx')) + \
                     glob(os.path.join(directory, '*.pdf')) + \
                     glob(os.path.join(directory, '*.ppt'))

    for file_path in document_files:
        try:
            # Extract text from document using Tika
            parsed = parser.from_file(file_path)
            #print( parsed["metadata"])
            text = parsed['content']
            if text is None:
                continue
            lines = text.splitlines()
            non_empty_lines = [line for line in lines if line.strip()]
            _title = ' '.join(non_empty_lines[:2]).replace('\t',' ').strip()
            text = re.sub(r'[\t\n\s]+', ' ', text).strip()
            generated_uuid = uuid.uuid5(uuid.NAMESPACE_OID, "{}_{}".format(project,os.path.basename(file_path)))
            components = file_path.split(os.path.sep)      
            nested_path = os.path.sep.join(components[3:])          
            # Add document info to the list
            indexed_documents.append(
                {
                        'id': str(generated_uuid),  
                        'name_s': _title,  
                        'filename_s': os.path.basename(file_path),  
                        'folder_s': nested_path,
                        '_text_': text,  # Index the extracted text
                        #'content_type_ss': parsed['metadata']['Content-Type'],  # Store content type
                        'dc_creator' : parsed['metadata']['dc:creator'],
                        'dcterms_modified' : parsed['metadata']['dcterms:modified'],
                        'project_s': project,  # Add project metadata
                        'workpackage_s': workpackage  # Add work package metadat
                }
            )
            print(f"Indexed: {file_path}")
        except Exception as err:
            print(file_path,err)

    return indexed_documents

def index_documents_from_json(json_file):
    with open(json_file) as f:
        data = json.load(f)
    indexed_documents = []
    for entry in data:
        project = entry['project']
        workpackage = entry['workpackage']
        docs_dir = entry['docs_dir']

        indexed_documents.extend(index_documents(docs_dir, project, workpackage))
    return indexed_documents

indexed_documents = index_documents_from_json(config_input)

print(product["data"])
with open(product["data"], 'w') as f:
    json.dump(indexed_documents, f, indent=4)