#!/usr/bin/env bash
set -euo pipefail

echo "Running data quality contract checks..."

required_paths=(
  "docs/data-dictionary.md"
  "docs/metric-spec.md"
  "api/schemas/movement-impact.schema.json"
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

echo "Data quality contract checks passed."
