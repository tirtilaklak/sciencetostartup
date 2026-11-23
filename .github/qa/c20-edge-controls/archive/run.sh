#!/usr/bin/env bash
set -euo pipefail
export QA_DIST="$PWD/dist" ARCHIVE_EVIDENCE_TIMEOUT_MS=180000
exec python3 .github/qa/c20-edge-controls/archive/eighth_archive.py
