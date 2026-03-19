#!/usr/bin/env bash
set -euo pipefail

echo "Running data quality contract checks..."

required_paths=(
  "docs/data-dictionary.md"
  "docs/metric-spec.md"
  "api/schemas/movement-impact.schema.json"
  "data/external/nfl_calendar_mapping.csv"
)

for path in "${required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path"
    exit 1
  fi
done

grep -q "movement_events" docs/data-dictionary.md || {
  echo "data-dictionary.md must document movement_events"
  exit 1
}

grep -q "Movement Impact Score" docs/metric-spec.md || {
  echo "metric-spec.md must define Movement Impact Score"
  exit 1
}

grep -q '"TeamImpactResponse"' api/schemas/movement-impact.schema.json || {
  echo "movement-impact schema must include TeamImpactResponse"
  exit 1
}

grep -q "nfl_calendar_mapping" docs/data-dictionary.md || {
  echo "data-dictionary.md must document nfl_calendar_mapping"
  exit 1
}

python3 - <<'PY'
import csv
from datetime import date

path = "data/external/nfl_calendar_mapping.csv"
allowed = {"offseason", "preseason", "regular", "postseason"}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))

if not rows:
  raise SystemExit("nfl_calendar_mapping.csv is empty")

prev = None
seen = set()
for row in rows:
  d = date.fromisoformat(row["calendar_date"])
  if row["season_phase"] not in allowed:
    raise SystemExit(f"invalid season_phase: {row['season_phase']}")
  if d in seen:
    raise SystemExit(f"duplicate calendar_date: {d}")
  seen.add(d)
  if prev is not None and (d - prev).days != 1:
    raise SystemExit(f"non-contiguous dates between {prev} and {d}")
  prev = d

print(f"validated calendar mapping rows: {len(rows)}")
PY

echo "Data quality contract checks passed."
