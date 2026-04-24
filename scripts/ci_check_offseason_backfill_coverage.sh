#!/usr/bin/env bash
set -euo pipefail

echo "Running offseason backfill coverage checks..."

BACKFILL_DIR="${OFFSEASON_BACKFILL_DIR:-data/processed/offseason/backfill_2022_2025}"
MODEL_OUTPUTS_PATH="${BACKFILL_DIR}/model_outputs_hierarchical.csv"
MOVEMENT_EVENTS_PATH="${BACKFILL_DIR}/movement_events.csv"

required_paths=(
  "${MODEL_OUTPUTS_PATH}"
  "${MOVEMENT_EVENTS_PATH}"
)

for path in "${required_paths[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "Missing required file: ${path}"
    exit 1
  fi
done

python3 - <<'PY'
import csv
import os
import sys
from collections import Counter
from pathlib import Path

backfill_dir = Path(os.environ.get("OFFSEASON_BACKFILL_DIR", "data/processed/offseason/backfill_2022_2025"))
model_outputs = backfill_dir / "model_outputs_hierarchical.csv"
movement_events = backfill_dir / "movement_events.csv"
expected = {2022, 2023, 2024, 2025}

with model_outputs.open(newline="", encoding="utf-8") as f:
    model_rows = list(csv.DictReader(f))

if not model_rows:
    raise SystemExit(f"{model_outputs} is empty")

model_seasons = {
    int((row.get("nfl_season") or "").strip())
    for row in model_rows
    if (row.get("nfl_season") or "").strip().isdigit()
}

missing_model_seasons = sorted(expected - model_seasons)
if missing_model_seasons:
    raise SystemExit(
        f"model outputs missing required seasons {missing_model_seasons}; "
        f"found={sorted(model_seasons)}"
    )

with movement_events.open(newline="", encoding="utf-8") as f:
    movement_rows = list(csv.DictReader(f))

if not movement_rows:
    raise SystemExit(f"{movement_events} is empty")

counts = Counter()
for row in movement_rows:
    season = (row.get("nfl_season") or "").strip()
    if season.isdigit():
        counts[int(season)] += 1

missing_movement = sorted(season for season in expected if counts.get(season, 0) <= 0)
if missing_movement:
    raise SystemExit(
        "movement_events has zero rows for seasons: "
        f"{missing_movement}; counts={dict(sorted(counts.items()))}"
    )

print(f"validated backfill model seasons: {sorted(model_seasons)}")
print(f"validated movement row counts by season: {dict((s, counts[s]) for s in sorted(expected))}")
PY

echo "offseason backfill coverage checks passed"
