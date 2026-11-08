"""Serve an immutable static artifact with production-like gzip for local audits."""
import argparse
import functools
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Server(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        self.directory = Path(directory).resolve()
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        url = urlsplit(self.path)
        path = (self.directory / unquote(url.path).lstrip('/')).resolve()
        if path != self.directory and self.directory not in path.parents:
            self.send_error(403)
            return
        if path.is_dir():
            if not url.path.endswith('/'):
                self.send_response(308)
                self.send_header('Location', url.path + '/' + ('?' + url.query if url.query else ''))
                self.end_headers()
                return
            path /= 'index.html'
        status = 200
        if not path.is_file():
            path, status = self.directory / '404.html', 404
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        media = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        compress = 'gzip' in self.headers.get('Accept-Encoding', '') and (media.startswith('text/') or path.suffix in ('.js', '.json', '.svg', '.xml'))
        if compress:
            data = gzip.compress(data, compresslevel=6, mtime=0)
        self.send_response(status)
        self.send_header('Content-Type', media + ('; charset=utf-8' if media.startswith('text/') else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Vary', 'Accept-Encoding')
        if compress:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if body:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18769)
    args = parser.parse_args()
    handler = functools.partial(Handler, directory=args.directory)
    with Server(('127.0.0.1', args.port), handler) as server:
        print(f'Static audit artifact: {args.directory.resolve()} on port {args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
