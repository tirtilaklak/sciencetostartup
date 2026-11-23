"""Serve a private A/B copy of the b799 Research shard pages."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
from subprocess import check_output
from tempfile import TemporaryDirectory
from time import sleep

REPO = Path(__file__).resolve().parents[3]
ARTIFACT = REPO / "output/b799-ledger-baseline"
SOURCE = "b799629a2a9c9fdee49e4b32b37e2ddae197ebe8"
PRODUCT = "b1133b04a25cb0d66d39f8836ee9635129816df9"
MANIFEST = "6edf60f384be1e9d7844d398ef755d9fb839e5130d69b707e92e08ae15241ec1"
SHARDS = ("research/data/assertions/1/index.html", "research/data/sources/6/index.html")
CASES = SHARDS + (
    "research/state-of-ai-data-labs/chapters/technical-landscape/index.html",
    "static-pages.css", "field-guide.css", "page-layout.css", "research.css", "native-details.js",
    "manifest.json",
)
MARKER = (b'<script>(()=>{const root=document.documentElement;'
          b'const sync=()=>root.toggleAttribute("data-ledger-fragment",'
          b'/^#(?:assertion|source)-/.test(location.hash));sync();'
          b'addEventListener("hashchange",sync);})();</script>\n')
RULE = (b'html[data-ledger-fragment] .research :is(.r-assertion,.r-source,.r-source-stub)'
        b'{content-visibility:visible;contain-intrinsic-size:none}\n')
HASH = lambda data: sha256(data).hexdigest()
server = run_path(str(REPO / "scripts/preview_server.py"))


def main():
    manifest_body = (ARTIFACT / "manifest.json").read_bytes()
    assert HASH(manifest_body) == MANIFEST
    commit = check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    parent = check_output(["git", "rev-parse", "HEAD^"], cwd=REPO, text=True).strip()
    changed = check_output(["git", "diff", "--name-only", parent, commit], cwd=REPO, text=True)
    assert commit == os.environ["GITHUB_SHA"] and parent == SOURCE
    assert set(changed.splitlines()) == {".github/qa/ledger-layout/server.py",
        ".github/qa/ledger-layout/probe.cjs", ".github/workflows/b799-ledger-layout-probe.yml"}
    tracked = check_output(["git", "diff", "--name-only", PRODUCT, SOURCE], cwd=REPO, text=True)
    assert tracked.splitlines() == ["tests/browser/finance-evidence.spec.js"]
    asset_hashes = json.loads(manifest_body)["sha256"]

    with TemporaryDirectory(prefix="s2s-b799-ledger-layout-", dir="/dev/shm") as tmp:
        root = Path(tmp)
        versions = {name: root / name for name in ("control", "stable")}
        receipts = {}
        for rel in CASES:
            data = (ARTIFACT / rel).read_bytes()
            assert rel == "manifest.json" or HASH(data) == asset_hashes[rel]
            test = data
            if rel in SHARDS:
                stylesheet = b'<link rel="stylesheet" href="/research.css">'
                assert data.count(stylesheet) == 1
                test = data.replace(stylesheet, MARKER + stylesheet)
            if rel == "research.css":
                test += b'\n' + RULE
            receipts[rel] = {"control": HASH(data), "stable": HASH(test)}
            for mode, body in (("control", data), ("stable", test)):
                path = versions[mode] / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)

        class Handler(server["Handler"]):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=versions["control"], **kwargs)

            def respond(self, body):
                mode = self.headers.get("X-QA-Ledger-Layout", "control")
                delay = self.headers.get("X-QA-Stylesheet-Delay-Ms", "0")
                if mode not in versions or delay not in ("0", "40", "90"):
                    return self.send_error(400)
                self.directory = versions[mode]
                if self.path == "/research.css" and delay != "0":
                    sleep(int(delay) / 1000)
                return super().respond(body)

        with server["Server"](("127.0.0.1", 0), Handler) as origin:
            print(json.dumps({
                "source": SOURCE, "applicable_product": PRODUCT, "control_manifest": MANIFEST,
                "qa_commit": commit, "run": os.environ["GITHUB_RUN_ID"],
                "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "build": json.loads(manifest_body)["build_id"],
                "origin": f"http://127.0.0.1:{origin.server_port}",
                "changes": receipts, "utc": datetime.now(timezone.utc).isoformat(),
            }), flush=True)
            origin.serve_forever()


if __name__ == "__main__":
    main()
