"""Local-only API used by source and packaged request tests; no CORS headers."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time


@contextmanager
def api_server():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            received.append({'method': self.command, 'path': self.path, 'headers': {key.lower(): value for key, value in self.headers.items()}, 'body': body})
            if self.path.startswith('/slow'):
                time.sleep(2)
            status = 401 if self.path.startswith('/unauthorized') else 302 if self.path.startswith('/redirect') else 200
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('X-Khana-Test', 'yes')
            if self.path.startswith('/cookie'):
                self.send_header('Set-Cookie', 'session=example; Path=/')
            if status == 302:
                self.send_header('Location', '/redirect-target')
            self.end_headers()
            try:
                self.wfile.write(json.dumps({'message': 'پاسخ API', 'method': self.command, 'path': self.path,
                                            'body': body.decode('utf-8', errors='replace')}, ensure_ascii=False).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_GET

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', received
    finally:
        server.shutdown(); server.server_close(); thread.join()


def api_spec(base_url):
    def operation(name, security=None):
        value = {'operationId': name, 'responses': {'200': {'description': 'Success'}, '401': {'description': 'Unauthorized'}}}
        if security is not None:
            value['security'] = security
        return value
    paths = {'/public': {'get': operation('public', [])}, '/bearer': {'get': operation('bearer', [{'token': []}])},
             '/basic': {'get': operation('basic', [{'basic': []}])}, '/api-key': {'get': operation('key', [{'key': []}])},
             '/query-key': {'get': operation('queryKey', [{'queryKey': []}])},
             '/oauth': {'get': operation('oauth', [{'oauth': ['read']}])},
             '/unauthorized': {'get': operation('unauthorized', [])}, '/slow': {'get': operation('slow', [])},
             '/redirect': {'get': operation('redirect', [{'token': []}])},
             '/echo/{id}': {'post': {**operation('echo', []),
                 'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string', 'default': '42'}},
                                {'name': 'q', 'in': 'query', 'schema': {'type': 'string', 'default': 'hello'}}],
                 'requestBody': {'required': True, 'content': {'application/json': {'schema': {'type': 'object'}, 'example': {'name': 'سلام'}}}}}}}
    return {'openapi': '3.0.3', 'info': {'title': 'Local Request Test', 'version': '1.0'}, 'servers': [{'url': base_url}],
            'paths': paths, 'components': {'securitySchemes': {
                'token': {'type': 'http', 'scheme': 'bearer'}, 'basic': {'type': 'http', 'scheme': 'basic'},
                'key': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'},
                'queryKey': {'type': 'apiKey', 'in': 'query', 'name': 'api_key'},
                'oauth': {'type': 'oauth2', 'flows': {'clientCredentials': {'tokenUrl': base_url + '/never-fetch-token', 'scopes': {'read': 'Read'}}}}}}}
