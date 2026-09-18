#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BOOT="$ROOT/plugins/resilient_public_data_collection/runtime_bootstrap.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

run_bootstrap() {
  local label="$1"
  local stdout_file="$2"
  local stderr_file="$3"
  shift 3

  set +e
  python3 "$BOOT" "$@" >"$stdout_file" 2>"$stderr_file"
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "FAIL: $label exited with code $rc" >&2
    cat "$stdout_file" >&2 || true
    cat "$stderr_file" >&2 || true
    return "$rc"
  fi
}

RUNTIME="$TMP/crawlee-runtime"
python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" --plan > "$TMP/plan.json"
grep -Fq '"requirement": "crawlee==1.10.1"' "$TMP/plan.json"
[[ ! -e "$RUNTIME" ]] || { echo "FAIL: plan mutated runtime"; exit 1; }

if python3 "$BOOT" --mode core --runtime-dir "$RUNTIME" --check-only > "$TMP/precheck.json"; then
  echo "FAIL: empty runtime unexpectedly READY" >&2
  exit 1
fi
grep -Fq '"state": "MISSING_RUNTIME"' "$TMP/precheck.json"

run_bootstrap "core install" "$TMP/install.json" "$TMP/install.stderr" --mode core --runtime-dir "$RUNTIME"
grep -Fq '"state": "READY"' "$TMP/install.json"
grep -Fq '"installed_version": "1.10.1"' "$TMP/install.json"

RUNTIME_PY="$(python3 - "$TMP/install.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["python_executable"])
PY
)"
"$RUNTIME_PY" - <<'PY'
import importlib.metadata
import importlib.util
assert importlib.metadata.version("crawlee") == "1.10.1"
assert importlib.util.find_spec("playwright") is None
from crawlee.crawlers import FileDownloadCrawler
assert FileDownloadCrawler
PY

# Force the fallback used on minimal Debian/Ubuntu hosts without ensurepip/python3-venv.
TARGET="$TMP/target-runtime"
run_bootstrap "target fallback install" "$TMP/target.json" "$TMP/target.stderr" --mode core --backend target --runtime-dir "$TARGET"
grep -Fq '"runtime_backend": "target"' "$TMP/target.json"
grep -Fq '"installed_version": "1.10.1"' "$TMP/target.json"

TARGET_PY="$(python3 - "$TMP/target.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["python_executable"])
PY
)"
"$TARGET_PY" - <<'PY'
import importlib.metadata
from crawlee.crawlers import FileDownloadCrawler
assert importlib.metadata.version("crawlee") == "1.10.1"
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

python3 "$BOOT" --mode core --runtime-dir "$TARGET" --offline > "$TMP/target-offline.json"
grep -Fq '"state": "READY"' "$TMP/target-offline.json"
grep -Fq '"runtime_backend": "target"' "$TMP/target-offline.json"

MISS="$TMP/missing"
if python3 "$BOOT" --mode core --runtime-dir "$MISS" --offline > "$TMP/miss.json"; then
  echo "FAIL: offline cache miss unexpectedly succeeded" >&2
  exit 1
fi
grep -Fq '"state": "OFFLINE_CACHE_MISS"' "$TMP/miss.json"
[[ ! -e "$MISS" ]] || { echo "FAIL: offline cache miss mutated runtime"; exit 1; }

FAIL_RUNTIME="$TMP/install-failure"
set +e
python3 "$BOOT" --mode core --backend target --runtime-dir "$FAIL_RUNTIME" > "$TMP/failure.json" 2> "$TMP/failure.stderr"
RC=$?
set -e
[[ "$RC" -eq 6 ]] || { echo "FAIL: expected exit 6, got $RC"; cat "$TMP/failure.json"; exit 1; }
grep -Fq '"state": "INSTALL_FAILED"' "$TMP/failure.json"
if grep -Fq "Traceback" "$TMP/failure.stderr"; then
  echo "FAIL: structured install failure leaked traceback" >&2
  exit 1
fi

echo "PASS: Semantier Crawlee venv/target fallback, offline reuse, and failure behavior"
