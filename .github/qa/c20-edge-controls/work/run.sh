#!/usr/bin/env bash
set -euo pipefail
bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
: "${QA_BASE_URL:?Set QA_BASE_URL to the immutable or public release host}"
origin="${QA_BASE_URL%/}"
root_output="${S2S_C20_WORK_OUTPUT:-output/c20-controls}"
manifest="$(node -p 'require(process.argv[1]).manifest_sha256' "$bundle_dir/expected.json")"
mkdir -p "$root_output/work-webkit-back"
exit_code=0
node "$bundle_dir/verify-downloads.cjs" "$root_output/work-downloads" || exit_code=1
node "$bundle_dir/work-back.cjs" "$origin" "$manifest" "$root_output/work-webkit-back" webkit-stock-bookmark \
  2>&1 | tee "$root_output/work-webkit-back/probe.log" || exit_code=1
exit "$exit_code"
