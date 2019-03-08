![MIT License](https://img.shields.io/badge/license-MIT-blue.svg) ![travis ci](https://travis-ci.org/usc-isi-i2/etk.svg?branch=master)

# datamart

```commandline
cd datamart
```

if you are using linux, refer here to remove 2 lines:
https://github.com/conda/conda/issues/6073#issuecomment-393200362

```
conda env create -f environment.yml
source activate datamart_env
git update-index --assume-unchanged datamart/resources/index_info.json

python -W ignore -m unittest discover
```

If you meet problems about level.db, please try the following commands:
If you have homebrew installed: `brew install leveldb`
otherwise:
```
pip install leveldb
CFLAGS='-mmacosx-version-min=10.7 -stdlib=libc++' pip install plyvel --no-cache-dir --global-option=build_ext --global-option="-I/usr/local/Cellar/leveldb/1.20_2/include/" --global-option="-L/usr/local/lib"
pip install rltk
```

#### When new packages were added:

Before commit: please run the following commands to update the dependencies config.
```
conda env export --no-build > environment.yml
pip freeze > requirements.txt
```
After pull: please run `conda env update -f environment.yml` to update the dependencies.


## Validate your schema
Dataset providers should validate their dataset schema against our json schema by the following
```commandline
python scripts/validate_schema.py --validate_json {path_to_json}
```
eg.
```commandline
$ python scripts/validate_schema.py --validate_json test/tmp/tmp.json
$ Valid json
```

## How to provide index for one data source

1. Prepare your dataset schema following [datamart index schema](https://paper.dropbox.com/doc/Datamart-Index-Schema--ARZ9ANxCYpvOOfTKxXGE9MI1Ag-0Uu03rDIUCttwS0x9GLCq)
 and validate it with the previous step

2. Create your materialization method by creating a subclass of [`materializer_base.py`](./datamart/materializers/materializer_base.py).
and put in `datamart/materializers`. See [README](./datamart/materializers/README.MD)

3. Have your dataset schema json `materialization.python_path` pointed to the materialization method. 
Take a look at [tmp.json](example/tmp/tmp.json#L10).

---

#### Python API:

##### There are three main APIs:
1. datamart.search(url: str, query: dict, data: pandas.DataFrame, send_data: bool=True) -> list[datamart.Dataset]
  - input:
    - url: for ISI's datamart it should be "isi-datamart"
    - query: a description json object for the target datasets
    - data: the original dataset to be augmented
    -send_data: meaningless for current ISI datamart
  - output: 
    - a list of datamart.Dataset objects, each is for a dataset indexed in Datamart
    
2. datamart.augment(original_data: pandas.DataFrame, augment_data: datamart.Dataset) -> pandas.DataFrame
  - input:
    - the original dataset to be augmented
    - the datamart.Dataset to be used for augmentation
  - output:
    - the augmented data
    
3. datamart.upload(description: dict, es_index: str=None) -> dict
  - input:
    - a description json for the dataset, including the url for the concrete data(e.g. an url for a csv file)
    - where to index(OPTIONAL) - used to toggle test/in-use datamart ES indices
  - output:
    - the final object indexed into datamart(with user provided description, inferred description, profiling info etc.)

(more information can be found under [wiki](https://datadrivendiscovery.org/wiki/display/work/Data+augmentation+working+group))

#### REST API documentation: [rest_example](example/rest_example/example.md)

#### Example of using current system:
- ##### Create metadata and index it on Elasticsearch, following: [Indexing demo](example/index.ipynb)
- ##### Query datamart, following: [Query demo](example/query_by_json.ipynb)
- ##### Dealing with TAXI example, following: [taxi_example](example/taxi_example/taxi_example.ipynb)
- ##### Dealing with FIFA example, following: [fifa_example](example/fifa_example/fifa_example.ipynb)
- ##### Dealing with Hall of Fame example, following: [hof_example](example/hof_example/hof_example.ipynb)


Note: Launch notebook: 
```
jupyter notebook test/index.ipynb
```
