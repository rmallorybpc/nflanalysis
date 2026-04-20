#!/usr/bin/env bash
set -u -o pipefail

failures=0

for season in 2022 2023 2024 2025; do
  echo "=== Fetching season ${season} ==="
  if ! python3 scripts/fetch_season_data.py --season "${season}"; then
    echo "[WARN] Season ${season} failed; continuing to next season"
    failures=$((failures + 1))
  fi
done

echo "=== All seasons fetched ==="

if [[ ${failures} -gt 0 ]]; then
  echo "[WARN] ${failures} season run(s) failed"
  exit 1
fi
