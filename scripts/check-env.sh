#!/usr/bin/env bash
# check-env.sh — validate .env against .env.example
#
# Usage:  bash scripts/check-env.sh [path-to-.env]
#
# Keys with an empty default in .env.example (e.g. LLM_API_KEY=) are REQUIRED.
# Keys with a non-empty default (e.g. BACKEND_PORT=8082) are optional warnings.
# Exits non-zero if any required key is missing from the target .env file.

set -euo pipefail

ENV_FILE="${1:-.env}"
EXAMPLE_FILE="$(dirname "$0")/../.env.example"
ERRORS=0
WARNINGS=0

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR  $ENV_FILE not found"
  exit 1
fi

while IFS= read -r line; do
  # Skip comments and blank lines
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${line// }" ]] && continue

  key="${line%%=*}"
  default="${line#*=}"

  if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    if [[ -z "$default" ]]; then
      echo "ERROR  missing required key: $key"
      ERRORS=$((ERRORS + 1))
    else
      echo "WARN   missing key (will use default): $key=$default"
      WARNINGS=$((WARNINGS + 1))
    fi
  fi
done < "$EXAMPLE_FILE"

if [[ $ERRORS -eq 0 ]]; then
  echo "OK     all required keys present ($WARNINGS warning(s))"
  exit 0
fi

echo "FAIL   $ERRORS required key(s) missing from $ENV_FILE"
exit 1
