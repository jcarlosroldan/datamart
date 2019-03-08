import copy
import typing
from json import dumps

from datamart.index_builder import IndexBuilder
from datamart.utilities.html_processer import HTMLProcesser, FILE_BLACK_LIST, TITLE_BLACK_LIST
from datamart.utilities.utils import Utils, ES_HOST, ES_PORT, PRODUCTION_ES_INDEX
from datamart.materializers.general_materializer import GeneralMaterializer
from datamart.materializers.parsers.html_parser import HTMLParser
from datamart.es_managers.query_manager import QueryManager
from scripts.generate_schema.wikitables.generate_wikitables_schema import generate_datasets_metadata as generate_wikitables_metadata


def generate_metadata(description: dict, ignore_html=False, enable_two_ravens_profiler=False) -> typing.List[dict]:
    """
    Step 1 for indexing, user provide a description with url for materializing,
    datamart will try to generate metadata, by materializing, profiling the data,
    and will return to the users to take a look or edit for final indexing.

    :param description: a dict, must have the key "materializer_arguments",
           description["materializer_arguments"] must have the key "url" which is a valid url pointing to the real data
    :return: List of dict(mostly only one dict in the list, unless cases like excel file with multiple sheets)
             Each dict is a metadata that can be indexed to elasticsearch
    """

    url = description['materialization_arguments']['url'].rstrip('/')
    if not (url and isinstance(url, str) and Utils.validate_url(url)):
        return []

    file_name = url.rsplit('/', 1)[-1].rsplit('.', 1)
    if not file_name:
        return []
    if len(file_name) == 2:
        file_suffix = file_name[1].split('#', 1)[0]
        if file_suffix.lower() in FILE_BLACK_LIST:
            return []
        if ignore_html:
            parser = GeneralMaterializer().type2parser.get(file_suffix.lower())
            if isinstance(parser, HTMLParser) or parser is None:
                return []

    file_name = file_name[0].replace('-', ' ').replace('_', ' ')
    if not description.get('title'):
        description['title'] = file_name

    if not description.get('url'):
        description['url'] = url

    description['materialization'] = {
        'python_path': 'general_materializer',
        'arguments': description['materialization_arguments']
    }
    del description['materialization_arguments']

    ib = IndexBuilder()

    meta_list = []
    parse_results = GeneralMaterializer().parse(description)
    for res in parse_results:
        try:
            df = res.dataframe
            idx = res.index
            if len(parse_results) > 1:
                sub_name = '(%s)' % res.name if res.name else ''
                if sub_name or description.get('title'):
                    description['title'] = description.get('title', '') + sub_name
            description['materialization']['arguments']['index'] = idx or 0
            # TODO: make use of res.metadata?
            indexed = ib.indexing_generate_metadata(
                description_path=description,
                data_path=df,
                enable_two_ravens_profiler=enable_two_ravens_profiler
            )
            meta_list.append(indexed)
        except Exception as e:
            print('IndexBuilder.indexing_generate_metadata, FAIL ON %d' % res.index, e)
            continue
    return meta_list


def bulk_generate_metadata(html_page: str,
                           description: dict=None,
                           enable_two_ravens_profiler=False
                           ) -> typing.List[typing.List[dict]]:
    """

    :param html_page:
    :param description:
    :param es_index:
    :return:
    """
    successed = []
    hp = HTMLProcesser(html_page)
    html_meta = hp.extract_description_from_meta()
    for text, href in hp.generate_a_tags_from_html():
        try:
            cur_description = copy.deepcopy(description) or {}
            if not Utils.validate_url(href):
                continue
            if not cur_description.get('title'):
                black_list = set(text.lower().split()).intersection(TITLE_BLACK_LIST)
                if not black_list:
                    cur_description['title'] = text.strip()
            if not cur_description.get('description'):
                cur_description['description'] = html_meta
            cur_description['materialization_arguments'] = {'url': href}
            # Not to extract html tables, otherwise there will be too many FPs:
            cur_metadata = generate_metadata(cur_description, ignore_html=True,
                                             enable_two_ravens_profiler=enable_two_ravens_profiler)
            if cur_metadata:
                successed.append(cur_metadata)
        except Exception as e:
            print(' - FAILED GENERATE METADATA ON \n\ttext = %s, \n\thref = %s \n%s' % (text, href, str(e)))
    return successed


def check_existence(materialization: dict, es_index: str = PRODUCTION_ES_INDEX):
    """
    Query ElasticSearch with materializer name and arguments. Currently, only works with
    "general_materializer" and "wikitables_materializer."
    return the datamart id if exists
    else return None
    :param url:
    :return: datamart_id or None
    """

    materializer = materialization['python_path']
    if materializer == "general_materializer":
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match_phrase": {
                                "materialization.python_path": materializer
                            }
                        },
                        {
                            "match_phrase": {
                                "materialization.arguments.url": materialization['arguments']['url']
                            }
                        },
                        {
                            "match_phrase": {
                                "materialization.arguments.index": materialization['arguments']['index']
                            }
                        }
                    ]
                }
            }
        }
    elif materializer == "wikitables_materializer":
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match_phrase": {
                                "materialization.python_path": materializer
                            }
                        },
                        {
                            "match_phrase": {
                                "materialization.arguments.url": materialization['arguments']['url']
                            }
                        },
                        {
                            "match_phrase": {
                                "materialization.arguments.xpath": materialization['arguments']['xpath']
                            }
                        }
                    ]
                }
            }
        }
    else:
        raise Exception(f'Do not know how to perform existence check for materializer: {materializer}')
    qm = QueryManager(es_host=ES_HOST, es_port=ES_PORT, es_index=es_index)
    res = qm.search(dumps(query))
    # TODO: how about return many results, should raise warning
    if res and res[0]:
        return int(res[0].get('_id'))


def upload(meta_list: typing.List[dict],
           es_index: str = PRODUCTION_ES_INDEX,
           deduplicate: bool = True,
           index_builder: IndexBuilder = None) -> typing.List[dict]:
    ib = index_builder or IndexBuilder()
    succeeded = []
    for meta in meta_list:
        try:
            Utils.validate_schema(meta)
            meta['datamart_status'] = 'not_profiled'
            if deduplicate:
                exist_id = check_existence(meta['materialization'], es_index=es_index)
                if exist_id:
                    success = ib.updating_send_trusted_metadata(metadata=meta,
                                                                es_index=es_index,
                                                                datamart_id=exist_id)
                else:
                    success = ib.indexing_send_to_es(metadata=meta, es_index=es_index)
            else:
                success = ib.indexing_send_to_es(metadata=meta, es_index=es_index)
            if success:
                succeeded.append(success)
        except Exception as e:
            print('UPLOAD FAILED: ', str(e))
            continue
    return succeeded


def bulk_upload(list_of_meta_list: typing.List[typing.List[dict]],
                es_index: str = PRODUCTION_ES_INDEX,
                deduplicate: bool = True
                ) -> typing.List[typing.List[dict]]:
    succeeded = []
    ib = IndexBuilder()
    for meta_list in list_of_meta_list:
        success_list = upload(meta_list, es_index, deduplicate, ib)
        if success_list:
            succeeded.append(success_list)
    return succeeded


def wikipedia_tables_metadata(url: str) -> typing.List[typing.Dict]:
    result = generate_wikitables_metadata(url)
    return result
