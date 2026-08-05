"""Semantic checks for M1-04 artifact references and embedded provenance."""
from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator, RefResolver

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/artifact-ref.v1.schema.json').read_text())
PROVENANCE_SCHEMA=json.loads((ROOT/'schemas/_defs/provenance.v1.schema.json').read_text())
RESOLVER=RefResolver(base_uri=(ROOT/'schemas/').as_uri()+'/',referrer=SCHEMA)
PROVENANCE_VALIDATOR=Draft202012Validator({
    '$ref':'#/$defs/provenance', '$defs':PROVENANCE_SCHEMA['$defs'],
})

PROVENANCE_FIELDS={'producers','request','environment','randomness','policies','extensions'}
PRODUCER_FIELDS={'id','kind','name','version','commit','build_profile','dirty','bundle_hash','parent_ids'}
REQUEST_FIELDS={'schema','behavior_profile','inputs','resolved_config_sha256'}
ENVIRONMENT_FIELDS={'python','rust','os','cpu','blas','thread_count','dependency_locks'}
RANDOMNESS_FIELDS={'seed','array_sources'}
POLICY_GROUPS={'fallback','conditioning','repairs','truncations','approximations'}
HASH_NAMED_FIELDS={'name','sha256'}
ARRAY_SOURCE_FIELDS={'name','source','sha256'}
POLICY_FIELDS={'name','parameters'}
REQUIRED_PRODUCER_KINDS={'platform','adapter','engine','algorithm'}

def validate_artifact_ref(value, producer=True, provenance=None):
    Draft202012Validator(SCHEMA,resolver=RESOLVER).validate(value)
    if value['relative_path'].endswith('/'):
        raise ValueError('artifact relative path must name a file')
    if value.get('dtype') in {'bool','int8','uint8'} and value.get('byte_order')!='not_applicable': raise ValueError('single-byte dtype requires not_applicable byte order')
    if value.get('dtype') not in {None,'bool','int8','uint8'} and value.get('byte_order')=='not_applicable': raise ValueError('multi-byte dtype requires byte order')
    if producer:
        allowed={'schema','content_schema','relative_path','mime_type','sha256','byte_length','producer','role','shape','dtype','byte_order','layout','extensions'}
        if set(value)-allowed: raise ValueError('artifact has unnamespaced fields')
    if provenance is not None and value['producer'] not in {p['id'] for p in provenance['producers']}: raise ValueError('artifact producer is absent from provenance')

def _reject_unrecognized_fields(value, allowed, description):
    unknown=set(value)-allowed
    if unknown:
        raise ValueError(f'{description} has unnamespaced fields: {sorted(unknown)}')

def validate_provenance(value, producer=True):
    """Validate embedded, execution-local provenance and its producer DAG."""
    PROVENANCE_VALIDATOR.validate(value)
    producers=value['producers']
    ids=[item['id'] for item in producers]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate provenance producer id')
    by_id={item['id']:item for item in producers}
    for item in producers:
        if producer:
            _reject_unrecognized_fields(item, PRODUCER_FIELDS, 'provenance producer')
        for parent_id in item['parent_ids']:
            if parent_id not in by_id:
                raise ValueError('provenance parent is absent')

    visiting=set()
    visited=set()
    def visit(producer_id):
        if producer_id in visiting:
            raise ValueError('provenance producer graph contains a cycle')
        if producer_id not in visited:
            visiting.add(producer_id)
            for parent_id in by_id[producer_id]['parent_ids']:
                visit(parent_id)
            visiting.remove(producer_id)
            visited.add(producer_id)
    for producer_id in by_id:
        visit(producer_id)
    if producer:
        _reject_unrecognized_fields(value, PROVENANCE_FIELDS, 'provenance')
        if not REQUIRED_PRODUCER_KINDS <= {item['kind'] for item in producers}:
            raise ValueError('provenance lacks a required producer kind')
        _reject_unrecognized_fields(value['request'], REQUEST_FIELDS, 'provenance request')
        _reject_unrecognized_fields(value['environment'], ENVIRONMENT_FIELDS, 'provenance environment')
        _reject_unrecognized_fields(value['randomness'], RANDOMNESS_FIELDS, 'provenance randomness')
        _reject_unrecognized_fields(value['policies'], POLICY_GROUPS, 'provenance policies')
        for item in value['request']['inputs'] + value['environment']['dependency_locks']:
            _reject_unrecognized_fields(item, HASH_NAMED_FIELDS, 'provenance hash input')
        for item in value['randomness']['array_sources']:
            _reject_unrecognized_fields(item, ARRAY_SOURCE_FIELDS, 'provenance array source')
        for group in POLICY_GROUPS:
            for item in value['policies'][group]:
                _reject_unrecognized_fields(item, POLICY_FIELDS, 'provenance policy')

def validate_artifact_collection(values, producer=True, provenance=None):
    paths=[item['relative_path'] for item in values]
    if len(paths)!=len(set(paths)): raise ValueError('duplicate artifact relative path')
    for item in values: validate_artifact_ref(item,producer,provenance)

def map_pybert_artifact_ref(domain, *, producer, role):
    """Map a PyBERT ArtifactRefV1 JSON wire object without changing it."""
    required={'name','schema','relativePath','mimeType','sha256','byteLength'}
    if set(domain)!=required: raise ValueError('unexpected PyBERT artifact fields')
    artifact={'schema':'sipi.artifact-ref.v1','content_schema':domain['schema'],'relative_path':domain['relativePath'],'mime_type':domain['mimeType'],'sha256':domain['sha256'],'byte_length':domain['byteLength'],'producer':producer,'role':role,'extensions':{'pybert.artifact-ref-v1':{'artifact':deepcopy(domain)}}}
    validate_artifact_ref(artifact)
    return artifact

def map_com_artifact(metadata, *, content_schema, mime_type, producer, role):
    if not all(key in metadata for key in ('relative_path','sha256','byte_length')): raise ValueError('COM manifest metadata incomplete')
    artifact={'schema':'sipi.artifact-ref.v1','content_schema':content_schema,'relative_path':metadata['relative_path'],'mime_type':mime_type,'sha256':metadata['sha256'],'byte_length':metadata['byte_length'],'producer':producer,'role':role,'extensions':{'agent-com.manifest':{'metadata':deepcopy(metadata)}}}
    validate_artifact_ref(artifact)
    return artifact
