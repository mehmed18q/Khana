"""Recognize local API definitions without resolving references or running YAML tags."""
from __future__ import annotations

import json
import math
import re

from ruamel.yaml import YAML
from ruamel.yaml.constructor import SafeConstructor
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode

METHODS = frozenset({'get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'})


class _APIConstructor(SafeConstructor):
    # OpenAPI examples with dates are JSON strings, not Python datetime objects.
    yaml_constructors = {**SafeConstructor.yaml_constructors,
                         'tag:yaml.org,2002:timestamp': SafeConstructor.construct_scalar}


def _json_value(value, ancestors=None, budget=None):
    """Bound alias expansion and accept only values representable in JSON."""
    ancestors = set() if ancestors is None else ancestors
    budget = [100_000] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or len(ancestors) > 100:
        raise ValueError('API definition is too complex.')
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in ancestors:
            raise ValueError('Cyclic YAML alias.')
        ancestors.add(identity)
        try:
            if isinstance(value, list):
                return [_json_value(item, ancestors, budget) for item in value]
            result = {}
            for key, item in value.items():
                # YAML commonly uses unquoted HTTP response codes as mapping keys.
                if not isinstance(key, (str, int)) or isinstance(key, bool):
                    raise ValueError('API object keys must be strings.')
                key = str(key)
                if key in result:
                    raise ValueError('Duplicate API object key.')
                result[key] = _json_value(item, ancestors, budget)
            return result
        finally:
            ancestors.remove(identity)
    raise ValueError('This YAML value cannot be represented in JSON.')


def _members(node):
    return {key.value: value for key, value in node.value if isinstance(key.value, str)} if isinstance(node, MappingNode) else {}


def api_definition(source: str, document_format: str) -> dict | None:
    if document_format not in {'JSON', 'YAML'} or not re.search(r'\b(?:openapi|swagger)\b', source):
        return None
    try:
        yaml = YAML(typ='safe', pure=True)
        yaml.Constructor = _APIConstructor
        node = yaml.compose(source)
        raw = json.loads(source) if document_format == 'JSON' else yaml.constructor.construct_document(node)
        if not isinstance(raw, dict):
            return None
        version = raw.get('openapi')
        if isinstance(version, str) and re.fullmatch(r'3\.[012]\.\d+(?:[-+][\w.-]+)?', version):
            label = f'OpenAPI {version}'
        elif raw.get('swagger') == '2.0':
            label = 'Swagger 2.0'
        else:
            return None
        spec = _json_value(raw)
        # Keep incomplete editing drafts as literal source until their basic
        # structure can be rendered. Swagger handles detailed schema diagnostics.
        if not isinstance(spec.get('info'), dict) or not isinstance(spec.get('paths', {}), dict):
            return None
        encoded = json.dumps(spec, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 5 * 1024 * 1024:
            return None
        paths = _members(_members(node).get('paths'))
        operations = []
        for path, item in spec.get('paths', {}).items():
            if not isinstance(item, dict):
                continue
            positions = _members(paths.get(path))
            for method, operation in item.items():
                if method not in METHODS or not isinstance(operation, dict):
                    continue
                position = positions.get(method)
                operations.append({'path': path, 'method': method, 'id': f'api-operation-{len(operations)}',
                                   'line': position.start_mark.line if position else 0,
                                   'end': position.end_mark.line if position else source.count('\n') + 1})
        def external_refs(value):
            if isinstance(value, dict):
                return any((key == '$ref' and isinstance(item, str) and not item.startswith('#')) or external_refs(item)
                           for key, item in value.items())
            return isinstance(value, list) and any(external_refs(item) for item in value)
        return {'spec': spec, 'label': label, 'operations': operations, 'externalRefs': external_refs(spec)}
    except (YAMLError, ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        # Broken YAML/JSON must remain readable and editable, including while typing.
        return None
