import json
from pathlib import Path
import tempfile
import unittest

from reader.documents import load_document, render_source
from reader.openapi_documents import api_definition


class OpenAPITests(unittest.TestCase):
    def test_json_versions_and_source_preservation(self):
        for key, version in [('swagger', '2.0'), ('openapi', '3.0.4'), ('openapi', '3.1.2'), ('openapi', '3.2.0')]:
            spec = {key: version, 'info': {'title': 'سلام API', 'version': '1'},
                    'paths': {'/pets': {'get': {'responses': {'200': {'description': 'OK'}}}}}}
            source = json.dumps(spec, indent=2, ensure_ascii=False)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'definition.json'; path.write_text(source)
                doc = load_document(path)
                self.assertEqual(doc.api['spec'], spec)
                self.assertEqual(doc.source, source)
                self.assertEqual(path.read_text(), source)
                operation = doc.api['operations'][0]
                self.assertEqual(operation['path'], '/pets')
                self.assertIn('"get"', source.splitlines()[operation['line']])
                self.assertFalse(doc.api['externalRefs'])
                self.assertIn('structured-source', doc.html)

    def test_yaml_numeric_response_keys_and_references(self):
        source = '''openapi: 3.0.3
info: {title: نمونه API, version: "1"}
paths:
  /pets:
    get:
      summary: فهرست pets
      responses:
        200:
          description: OK
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Pet'}
components:
  schemas:
    Pet: {type: object, properties: {name: {type: string}, born: {type: string, example: 2026-01-01}}}
'''
        api = api_definition(source, 'YAML')
        self.assertEqual(api['spec']['paths']['/pets']['get']['responses']['200']['description'], 'OK')
        self.assertFalse(api['externalRefs'])
        self.assertEqual(api['spec']['components']['schemas']['Pet']['properties']['born']['example'], '2026-01-01')
        self.assertEqual(api['operations'][0]['line'], 5)
        self.assertTrue(api_definition(source.replace('#/components/schemas/Pet', './pet.yaml'), 'YAML')['externalRefs'])

    def test_ordinary_broken_and_unsafe_documents_stay_literal(self):
        cases = [('JSON', '{"openapi":'), ('YAML', 'openapi: [broken'), ('JSON', '{"openapi":"library-name"}'),
                 ('YAML', 'nested: {openapi: 3.0.3}'), ('YAML', 'swagger: 2.0\ninfo: {}'),
                 ('YAML', 'openapi: 3.0.3\ninfo: !!python/object:example {}'),
                 ('YAML', 'openapi: 3.0.3\ninfo: &a {title: *a}'),
                 ('JSON', '{"openapi":"3.0.3","info":{},"example":NaN}'),
                 ('YAML', 'openapi: 3.0.3\ninfo: {}\n---\nother: doc'),
                 ('YAML', 'openapi: 3.0.3\ninfo: {}\npaths: []')]
        for fmt, source in cases:
            with self.subTest(source=source):
                self.assertIsNone(render_source(source, fmt)['api'])

    def test_yaml_alias_expansion_is_bounded(self):
        source = 'openapi: 3.0.3\ninfo: {}\nx-0: &a0 [one, two]\n'
        source += '\n'.join(f'x-{i}: &a{i} [*a{i-1}, *a{i-1}, *a{i-1}, *a{i-1}]' for i in range(1, 12))
        self.assertIsNone(api_definition(source, 'YAML'))


if __name__ == '__main__':
    unittest.main()
