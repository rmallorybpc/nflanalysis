#!/usr/bin/env bash
set -euo pipefail

# Execute the repo's contract checks as the local Final/orchestrator entrypoint.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "=== Final orchestrator started: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ==="

CHECKS=(
  "scripts/ci_check_data_quality.sh"
  "scripts/ci_check_dashboard_contracts.sh"
  "scripts/ci_check_model_regression_contract.sh"
)

for check in "${CHECKS[@]}"; do
  if [[ ! -f "${check}" ]]; then
    echo "ERROR: Missing check script: ${check}"
    echo "FINAL_STATUS: FAIL"
    exit 1
  fi

  echo "--- Running ${check} ---"
  set +e
  bash "${check}"
  code=$?
  set -e

  if [[ ${code} -ne 0 ]]; then
    echo "--- FAILED ${check} (exit ${code}) ---"
    echo "FINAL_STATUS: FAIL"
    exit "${code}"
  fi

  echo "--- PASSED ${check} ---"
done

echo "=== Final orchestrator completed successfully ==="
echo "FINAL_STATUS: PASS"
