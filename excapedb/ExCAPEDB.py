import pandas as pd
from  rdkit  import  Chem

class ExCAPEDB():
    def __init__(self,path, file_in='pubchem.chembl.dataset4publication_inchi_smiles.tsv.xz',file_patched='pubchem.chembl.dataset4publication_inchi_smiles_v2.tsv'):
        self.zenodo = "https://zenodo.org/record/173258/files/pubchem.chembl.dataset4publication_inchi_smiles.tsv.xz?download=1"
        self.path = path
        self.file = "{}/{}".format(path,file_in)
        self.file_patched = "{}/{}".format(path,file_patched)
        self.id_tag='Original_Entry_ID'
        self.db_tag='DB'
        self.smi_tag='SMILES'
        self.inchikey_tag='Ambit_InchiKey'
        self.inchi_tag='InChI'
        self.id_index  = None
        self.db_index  = None
        self.smi_index = None
        self.inchikey_index = None
        self.inchi_index=None
        self.smiles_errors = {}
        
    def getInchiKey(self,line):
        if line is None:
            return None
        return line[self.inchikey_index]
    
    def getInchi(self,line):
        if line is None:
            return None
        return line[self.inchi_index]
    
    def getSmiles(self,line):
        if line is None:
            return None
        return line[self.smi_index]
    
    def getDB(self,line):
        if line is None:
            return None
        db = line[self.db_index]
        if db.startswith("pubchem"):
            db="pubchem"
        return db    
    
    def getIdentifier(self,line):
        if line is None:
            return None
        return line[self.id_index]    
    
    def read(self,process=None,_max_records=100,process_header=None):
        import lzma

        header=[]
        r=0
        with lzma.open(self.file, mode='rt') as file:
            prev_line=None
            for line in file:
                line = line.strip().split("\t")
                if r==0:
                    header=line
                    self.id_index=line.index(self.id_tag)
                    self.db_index=line.index(self.db_tag)
                    self.smi_index=line.index(self.smi_tag)
                    self.inchi_index=line.index(self.inchi_tag)
                    self.inchikey_index=line.index(self.inchikey_tag)
                    if not process_header is None:
                        process_header(header)
                    print(line)
                else:    
                    if process is None:
                        print(line[self.id_index])
                        print(line[self.db_index])
                        print(line[self.smi_index])
                    else:
                        process(r,line,prev_line)
                    prev_line=line    
                    if _max_records>0 and r>_max_records:
                        break
                r=r+1        
                
    def replace(self,line, smiles,inchikey,inchi)    :
        line[self.smi_index]=smiles
        line[self.inchikey_index]=inchikey
        line[self.inchi_index]=inchi
        return line
        
    def check_smiles(self,num,line,prev_line=None):
        is_error=False
        _id = self.getIdentifier(line)
        _db = self.getDB(line)
        #we have checked this one already
        if (_id == self.getIdentifier(prev_line)):
            return
        
        try:
            if _id in self.smiles_errors[_db]:
                return
        except:
            pass

        try:
            smiles = self.getSmiles(line)
            m = Chem.MolFromSmiles(smiles)
            if m == None :
                is_error=True
        except ValueError as e:
            is_error=True
            
        if is_error:    
            if not _db in self.smiles_errors:
                self.smiles_errors[_db] = []    
            
            self.smiles_errors[self.getDB(line)].append(_id)  
            
    def error_file(self,db):
        return "{}/errors_{}.txt".format(self.path,db)
        
    def write_errors(self):
        for db in self.smiles_errors:
            tmp=pd.DataFrame({"id" : self.smiles_errors[db]})
            file = self.error_file(db)
            print(file)
            tmp.to_csv(file,index=False,sep="\t")
            
    def read_errors(self):
        for db in ["pubchem","chembl20"]:
            file = self.error_file(db)
            tmp = pd.read_csv(file,sep="\t")            
            self.smiles_errors[db]=tmp["id"].values