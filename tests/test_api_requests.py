import base64
import json
import unittest

from reader.api_requests import parse_request


class ApiRequestTests(unittest.TestCase):
    def test_body_and_explicit_auth_headers_are_preserved(self):
        data = {
            "url": "https://example.test/v1/items?name=سلام",
            "method": "post",
            "headers": {
                "Authorization": "Bearer example",
                "Cookie": "session=example",
                "Host": "spoofed",
                "Content-Length": "999",
            },
            "body": base64.b64encode("متن".encode()).decode(),
        }
        url, method, headers, body = parse_request(json.dumps(data))
        self.assertEqual(url.host(), "example.test")
        self.assertEqual(method, "POST")
        self.assertEqual(
            dict(headers), {b"Authorization": b"Bearer example", b"Cookie": b"session=example"}
        )
        self.assertEqual(body, "متن".encode())

    def test_invalid_urls_methods_headers_and_bodies_are_rejected(self):
        base = {"url": "https://example.test", "method": "GET"}
        cases = [
            dict(url=value)
            for value in [
                "file:///etc/passwd",
                "/relative",
                "ftp://example.test",
                "https://user:secret@example.test",
                "https://example.test/#fragment",
                "http://",
            ]
        ]
        cases += [
            {"method": "CONNECT"},
            {"headers": {"X-Test": "a\r\nAuthorization: secret"}},
            {"headers": {"Invalid Header": "value"}},
            {"headers": {"X-Test": 1}},
            {"body": "invalid base64"},
            {"body": "aGVsbG8="},
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(ValueError):
                parse_request(json.dumps({**base, **update}))


if __name__ == "__main__":
    unittest.main()
