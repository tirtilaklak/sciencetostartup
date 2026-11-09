"""Build into a temporary directory and serve the exact artifact for browser QA."""
import argparse
import functools
import http.server
import json
import os
import tempfile
from pathlib import Path

from observatory import build


class BrowserQAServer(http.server.ThreadingHTTPServer):
    # Several browsers can request their asset burst at once. The stdlib's
    # five-connection backlog can reset requests before a handler starts.
    request_queue_size = 128
    daemon_threads = True


class ArtifactHandler(http.server.SimpleHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # Aborted stale-context requests are an intentional browser test.
            pass

    def log_message(self, format, *args):
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18766)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="sciencetostartup-browser-") as temporary:
        target = Path(os.environ["QA_DIST"]).resolve() if os.environ.get("QA_DIST") else Path(temporary)
        if not os.environ.get("QA_DIST"):
            build(json.loads((root / "data/canonical.json").read_text()), target)
        handler = functools.partial(ArtifactHandler, directory=str(target))
        server = BrowserQAServer(("127.0.0.1", args.port), handler)
        print(f"Browser QA artifact: {target}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
