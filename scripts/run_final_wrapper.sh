#!/usr/bin/env bash
# scripts/run_final_wrapper.sh
# Attempts to locate and run the Final/orchestrator runner from common locations.
set -euo pipefail

LOG_DIR="triage"
mkdir -p "${LOG_DIR}"
FINAL_LOG=$(ls "${LOG_DIR}"/final_run_*.log 2>/dev/null | tail -n1 || echo "${LOG_DIR}/final_run_$(date -u +%Y%m%dT%H%M%SZ).log")
echo "=== run_final_wrapper started: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" | tee -a "${FINAL_LOG}"

CANDIDATES=(
  "./run_final.sh"
  "./scripts/run_final.sh"
  "./scripts/orchestrator.sh"
  "./bin/final"
  "./tools/final"
  "final"
  "./run_final"
  "./scripts/run_final"
)

FOUND_CMD=""
for cmd in "${CANDIDATES[@]}"; do
  if [[ "${cmd}" != ./* && "${cmd}" != */* ]]; then
    if command -v "${cmd}" >/dev/null 2>&1; then
      FOUND_CMD="${cmd}"
      break
    fi
  else
    if [ -x "${cmd}" ]; then
      FOUND_CMD="${cmd}"
      break
    fi
  fi
done

if [ -z "${FOUND_CMD}" ]; then
  echo "ERROR: No Final/orchestrator runner found in candidates." | tee -a "${FINAL_LOG}"
  echo "Searched candidates:" | tee -a "${FINAL_LOG}"
  for c in "${CANDIDATES[@]}"; do echo "  - ${c}" | tee -a "${FINAL_LOG}"; done
  echo "If the runner exists in CI only, run the CI job and upload the triage log. Otherwise, place the runner script/binary in one of the candidate locations." | tee -a "${FINAL_LOG}"
  exit 2
fi

echo "Found runner: ${FOUND_CMD}" | tee -a "${FINAL_LOG}"
set +e
"${FOUND_CMD}" 2>&1 | tee -a "${FINAL_LOG}"
EXIT_CODE=$?
set -e
echo "Runner exit code: ${EXIT_CODE}" | tee -a "${FINAL_LOG}"
if [ "${EXIT_CODE}" -ne 0 ]; then
  echo "Runner failed with exit code ${EXIT_CODE}. Inspect ${FINAL_LOG} for details." | tee -a "${FINAL_LOG}"
  exit "${EXIT_CODE}"
fi

echo "Runner completed successfully. Log: ${FINAL_LOG}"
exit 0
