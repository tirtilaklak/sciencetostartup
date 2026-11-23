#!/usr/bin/env bash
set -euo pipefail
repo_dir=$PWD
bundle_dir=$repo_dir/.github/qa/c20-edge-controls/acceptance
chrome_binary=$(node -e 'process.stdout.write(require("playwright").chromium.executablePath())')
firefox_binary=$(node -e 'process.stdout.write(require("playwright").firefox.executablePath())')
exec python3 "$bundle_dir/run_acceptance.py" --base-url "$QA_BASE_URL" --output-dir "$repo_dir/output/c20-controls/acceptance" \
    --chromium "$chrome_binary" --firefox "$firefox_binary" --playwright-module "$repo_dir/node_modules/playwright"
