import json
import unittest
from unittest.mock import patch
from xml.dom import minidom

from ruamel.yaml import YAML

from reader.source_formatting import beautify_source


class SourceFormattingTests(unittest.TestCase):
    def test_json_preserves_number_tokens_keys_strings_and_order(self):
        source = r'{"id":9007199254740993123,"n":1.234567890123456789,"x":1e-9999,"same":1,"same":2,"text":"سلام\n\u0041 \\","empty":[],"items":[{},true,null]}'
        result = beautify_source(source, "JSON")

        def tokens(text):
            return json.loads(text, parse_float=str, parse_int=str, object_pairs_hook=list)

        self.assertEqual(tokens(source), tokens(result))
        self.assertIn('  "id": 9007199254740993123,\n', result)
        self.assertIn(r"\u0041", result)
        self.assertEqual(result, beautify_source(result, "JSON"))

    def test_json_rejects_invalid_source(self):
        for source in ('{"x":}', "[1,]", '{"n":NaN}', "true false", ""):
            with self.subTest(source=source), self.assertRaises(ValueError):
                beautify_source(source, "JSON")

    def test_yaml_preserves_comments_quotes_anchors_scalars_and_documents(self):
        source = '# Header\nbase: &defaults\n     name: "سلام"\n     number: 1.234567890123456789\n     enabled: yes\napp:\n     <<: *defaults\n     values: [1,2] # Keep\n     text: |-\n          first\n          second\n---\n# Second document\nname: last\n'
        result = beautify_source(source, "YAML")
        self.assertIn('  name: "سلام"', result)
        for text in (
            "# Header",
            "# Keep",
            "# Second document",
            "&defaults",
            "*defaults",
            "1.234567890123456789",
            "enabled: yes",
            "|-",
        ):
            self.assertIn(text, result)

        def load(source):
            return list(YAML(typ="rt", pure=True).load_all(source))

        self.assertEqual(load(source), load(result))
        self.assertEqual(result, beautify_source(result, "YAML"))

    def test_yaml_versions_tags_and_aliases_are_not_constructed(self):
        source = "%YAML 1.1\n---\nflag: yes\nn: 012\ntag: !Custom data\ncycle: &a [*a]\n---\nflag: true\n"
        result = beautify_source(source, "YAML")
        for text in ("%YAML 1.1", "flag: yes", "n: 012", "!Custom data", "&a", "*a"):
            self.assertIn(text, result)
        self.assertEqual(result, beautify_source(result, "YAML"))
        for source in ("", "# Just a comment\n"):
            self.assertEqual(source, beautify_source(source, "YAML"))
        with self.assertRaisesRegex(ValueError, "line"):
            beautify_source("items: [1,", "YAML")

    def test_xml_preserves_mixed_text_cdata_comments_namespaces_and_space(self):
        source = '<?xml version="1.0" encoding="UTF-8"?><r xmlns:x="urn:test"><!--Keep--><?info test?><p>Hello <b>world</b>!</p><x:item a="1"><inner/></x:item><raw><![CDATA[a < b]]></raw><keep xml:space="preserve"> <b/> </keep><between><b>A</b> <b>B</b></between><nbsp><b/>\u00a0<b/></nbsp></r>'
        result = beautify_source(source, "XML")
        for text in (
            "<p>Hello <b>world</b>!</p>",
            "<!--Keep-->",
            "<?info test?>",
            "<![CDATA[a < b]]>",
            '<keep xml:space="preserve"> <b/> </keep>',
            'xmlns:x="urn:test"',
            "<between><b>A</b> <b>B</b></between>",
            "<nbsp><b/>\u00a0<b/></nbsp>",
        ):
            self.assertIn(text, result)
        self.assertIn('\n  <x:item a="1">\n    <inner/>\n  </x:item>', result)
        self.assertTrue(result.startswith('<?xml version="1.0" encoding="UTF-8"?>\n'))
        with minidom.parseString(result) as parsed:
            self.assertEqual(
                parsed.getElementsByTagName("p")[0].toxml(), "<p>Hello <b>world</b>!</p>"
            )
        self.assertEqual(result, beautify_source(result, "XML"))

    def test_xml_rejects_bad_markup_and_dtd(self):
        for source in ("<r><x></r>", '<!DOCTYPE r [<!ENTITY a "hello">]><r>&a;</r>'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                beautify_source(source, "XML")

    def test_unsupported_formats_are_not_rewritten(self):
        for fmt in ("Markdown", "HTML", "Word", "PDF", "LOG", "CONF"):
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                beautify_source("Text", fmt)

    def test_expanded_output_limit(self):
        with patch("reader.source_formatting.MAX_FILE_BYTES", 35):
            for fmt, source in [
                ("JSON", "[[[[[1,2,3,4]]]]]"),
                ("YAML", "values: [1,2,3,4,5,6,7,8,9,0]"),
            ]:
                with self.subTest(fmt=fmt), self.assertRaisesRegex(ValueError, "limit"):
                    beautify_source(source, fmt)


if __name__ == "__main__":
    unittest.main()
