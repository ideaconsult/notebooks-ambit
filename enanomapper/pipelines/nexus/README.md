
This is a ploomber pipeline [1] , illustrating retrieval from enanomapper database and saving the results into NeXus file.

copy env_example.yaml to env.yaml and edit accordingly

Run 

```
ploomber build
```

The pipeline is configured to generate Jupyter notebook in products folder and will also generate .nxs file .
You can explore NeXus files with h5web or nexpy.

[1] https://ploomber.io/
[1] https://www.nexusformat.org/