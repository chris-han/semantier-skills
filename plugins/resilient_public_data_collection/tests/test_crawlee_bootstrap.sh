#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BOOT="$ROOT/plugins/resilient_public_data_collection/runtime_bootstrap.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RUNTIME="$TMP/crawlee-runtime"

python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" --plan > "$TMP/plan.json"
grep -Fq '"requirement": "crawlee==1.10.1"' "$TMP/plan.json"
[[ ! -e "$RUNTIME" ]] || { echo "FAIL: plan mutated runtime"; exit 1; }

if python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" --check-only > "$TMP/precheck.json"; then
  echo "FAIL: empty runtime unexpectedly READY" >&2
  exit 1
fi
grep -Fq '"state": "MISSING_RUNTIME"' "$TMP/precheck.json"

python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" > "$TMP/install.json"
grep -Fq '"state": "READY"' "$TMP/install.json"
grep -Fq '"installed_version": "1.10.1"' "$TMP/install.json"

VENV_PY="$RUNTIME/venv/bin/python"
"$VENV_PY" - <<'PY'
import importlib.metadata
import importlib.util
assert importlib.metadata.version("crawlee") == "1.10.1"
assert importlib.util.find_spec("playwright") is None
from crawlee.crawlers import FileDownloadCrawler
assert FileDownloadCrawler
PY

export PIP_NO_INDEX=1
export PIP_INDEX_URL="http://127.0.0.1:9/simple"
export PIP_FIND_LINKS="$TMP/empty-wheelhouse"
export HTTP_PROXY="http://127.0.0.1:9"
export HTTPS_PROXY="http://127.0.0.1:9"
export ALL_PROXY="http://127.0.0.1:9"
mkdir -p "$PIP_FIND_LINKS"

python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" --offline > "$TMP/offline.json"
grep -Fq '"state": "READY"' "$TMP/offline.json"
grep -Fq '"installed_dependency": false' "$TMP/offline.json"

python3 "$BOOT" --mode browser --runtime-dir "$RUNTIME" --plan > "$TMP/browser-plan.json"
grep -Fq '"requirement": "crawlee[playwright]==1.10.1"' "$TMP/browser-plan.json"
grep -Fq '"browser_extra": true' "$TMP/browser-plan.json"

MISS="$TMP/missing"
if python3 "$BOOT" --mode core --runtime-dir "$MISS" --offline > "$TMP/miss.json"; then
  echo "FAIL: offline cache miss unexpectedly succeeded" >&2
  exit 1
fi
grep -Fq '"state": "OFFLINE_CACHE_MISS"' "$TMP/miss.json"
[[ ! -e "$MISS" ]] || { echo "FAIL: offline cache miss mutated runtime"; exit 1; }

FAIL_RUNTIME="$TMP/install-failure"
set +e
python3 "$BOOT" --mode core --runtime-dir "$FAIL_RUNTIME" > "$TMP/failure.json" 2> "$TMP/failure.stderr"
RC=$?
set -e
[[ "$RC" -eq 6 ]] || { echo "FAIL: expected exit 6, got $RC"; cat "$TMP/failure.json"; exit 1; }
grep -Fq '"state": "INSTALL_FAILED"' "$TMP/failure.json"
if grep -Fq "Traceback" "$TMP/failure.stderr"; then
  echo "FAIL: structured install failure leaked traceback" >&2
  exit 1
fi

echo "PASS: Semantier Crawlee lazy bootstrap, offline reuse, and failure behavior"
