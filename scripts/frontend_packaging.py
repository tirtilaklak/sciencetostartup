"""Python build orchestration for the pinned, build-time frontend transformer."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ESBUILD_VERSION = "0.28.2"


def package_frontend(javascript=None, stylesheets=None):
    node = shutil.which("node")
    if not node:
        raise ValueError("Frontend packaging requires Node.js 22 or newer. Install Node.js, then run npm ci in the repository root.")
    request = {"javascript": javascript or {}, "stylesheets": stylesheets or {}}
    try:
        result = subprocess.run(
            [node, str(ROOT / "scripts/frontend_packaging.mjs")],
            input=json.dumps(request, ensure_ascii=False), text=True,
            capture_output=True, cwd=ROOT, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Frontend packaging could not run. Check Node.js 22+ and run npm ci in the repository root.") from error
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Frontend packaging failed. Run npm ci in the repository root.")
    try:
        output = json.loads(result.stdout)
        if output["version"] != ESBUILD_VERSION:
            raise ValueError("Frontend packaging returned a different esbuild version; run npm ci.")
        for family in ("javascript", "stylesheets"):
            if set(output[family]) != set(request[family]) or not all(isinstance(v, str) for v in output[family].values()):
                raise ValueError("Frontend packaging returned incomplete output.")
        return output
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Frontend packaging returned invalid output.") from error


def minify_javascript(source):
    return package_frontend(javascript={"source": source})["javascript"]["source"]


def minify_css(source):
    return package_frontend(stylesheets={"source": source})["stylesheets"]["source"]
