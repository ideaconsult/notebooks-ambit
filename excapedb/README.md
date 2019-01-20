# ExCAPEDB v1 fix
ExCAPEDB is described in

> Sun J, Jeliazkova N, Chupakin V, Golib-Dzib J-F, Engkvist O, Carlsson L, Wegner J, Ceulemans H, Georgiev I, Jeliazkov V, Kochev N, Ashby TJ, Chen H: ExCAPE-DB: an integrated large scale dataset facilitating Big Data analysis in chemogenomics. J Cheminform 2017, 9:17. https://jcheminf.biomedcentral.com/articles/10.1186/s13321-017-0203-5

The original release at Zenodo https://zenodo.org/record/173258 contains a number of broken SMILES. 

This folder contains a Jupyter notebook, fixing the SMILES as follows:

- Downloads the file from Zenodo
- Check if RDKit is happy with the SMILES
- If not, retrieves the MOL files from the original source (PubChem or ChEMBL)
- Runs standadization with `ambitcli`
- Patches the Zenodo file with the new SMILES


### The ExCAPEDB file with fixed SMILES errors is available at https://zenodo.org/record/2543724  `pubchem.chembl.dataset4publication_inchi_smiles_v2.tsv.xz`




