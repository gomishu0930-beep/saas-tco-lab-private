#!/bin/sh

set -u

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
schema_temp_dir=$(mktemp -d)
result=0

cleanup() {
  rm -rf -- "$schema_temp_dir"
}
trap cleanup EXIT INT TERM

run_check() {
  label=$1
  shift
  echo "==> $label"
  if "$@"; then
    echo "<== PASS: $label"
  else
    echo "<== FAIL: $label"
    result=1
  fi
}

cd "$repo_dir" || exit 1

run_check "Python tests" uv run pytest
run_check "Python lock" uv lock --check
run_check "Schema export" uv run python scripts/export_schemas.py --output-dir "$schema_temp_dir"
run_check "Schema diff" diff -ru schemas "$schema_temp_dir"
run_check "Site tests" sh -c 'cd site && npm test'
run_check "Site lint" sh -c 'cd site && npm run lint'
run_check "Dependency audit" sh -c 'cd site && npm audit --audit-level=moderate'
run_check "Secret scan" gitleaks dir . --redact --no-banner --no-color

if [ "$result" -eq 0 ]; then
  echo "CHECK-ALL: PASS"
else
  echo "CHECK-ALL: FAIL"
fi
exit "$result"
