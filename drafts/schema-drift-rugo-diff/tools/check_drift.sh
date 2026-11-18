#!/usr/bin/env bash
# Usage: check_drift.sh BASELINE CANDIDATE
# Fails on breaking drift (a column removed or retyped). New columns are fine.
set -uo pipefail

report=$(rugo diff --json "$1" "$2") || true
[ -n "$report" ] || { echo "rugo diff produced no report" >&2; exit 2; }

echo "$report" | jq -r '
  (.columns_added[]   | "  + added    \(.)  (compatible)"),
  (.columns_removed[] | "  - removed  \(.)  (BREAKING)"),
  (.columns_changed[] | "  ~ changed  \(.name): \(.left_type) -> \(.right_type)  (BREAKING)")'

breaking=$(echo "$report" | jq '(.columns_removed | length) + (.columns_changed | length)')
if [ "$breaking" -gt 0 ]; then
  echo "$breaking breaking change(s)"
  exit 1
fi
echo "no breaking changes"
