#!/usr/bin/env bash
set -euo pipefail

echo "Running data quality contract checks..."

required_paths=(
  "docs/data-dictionary.md"
  "docs/metric-spec.md"
  "api/schemas/movement-impact.schema.json"
  "data/external/nfl_calendar_mapping.csv"
  "data/processed/movement_events.csv"
  "data/processed/player_dimension.csv"
  "data/processed/team_week_outcomes.csv"
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

python3 - <<'PY'
import csv

path = "data/processed/movement_events.csv"
required = {
  "move_id",
  "event_date",
  "effective_date",
  "move_type",
  "player_id",
  "from_team_id",
  "to_team_id",
  "nfl_season",
  "season_phase",
  "nfl_week",
  "ingested_at",
}
allowed_types = {"trade", "free_agency"}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))

if not rows:
  raise SystemExit("movement_events.csv is empty")

missing = required - set(rows[0].keys())
if missing:
  raise SystemExit(f"movement_events.csv missing required columns: {sorted(missing)}")

seen = set()
for row in rows:
  move_id = row["move_id"].strip()
  if not move_id:
    raise SystemExit("movement_events.csv contains empty move_id")
  if move_id in seen:
    raise SystemExit(f"movement_events.csv contains duplicate move_id: {move_id}")
  seen.add(move_id)

  move_type = row["move_type"].strip()
  if move_type not in allowed_types:
    raise SystemExit(f"invalid move_type: {move_type}")

print(f"validated movement events rows: {len(rows)}")
PY

python3 - <<'PY'
import csv

path = "data/processed/player_dimension.csv"
required = {
  "player_id",
  "full_name",
  "position_group",
  "position",
  "birth_date",
  "rookie_year",
  "experience_years",
  "active_status",
  "source",
  "normalized_at",
}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))

if not rows:
  raise SystemExit("player_dimension.csv is empty")

missing = required - set(rows[0].keys())
if missing:
  raise SystemExit(f"player_dimension.csv missing required columns: {sorted(missing)}")

seen = set()
for row in rows:
  player_id = row["player_id"].strip()
  if not player_id:
    raise SystemExit("player_dimension.csv contains empty player_id")
  if player_id in seen:
    raise SystemExit(f"player_dimension.csv contains duplicate player_id: {player_id}")
  seen.add(player_id)

print(f"validated player dimension rows: {len(rows)}")
PY

python3 - <<'PY'
import csv

path = "data/processed/team_week_outcomes.csv"
required = {
  "team_id",
  "nfl_season",
  "nfl_week",
  "games_played",
  "wins",
  "losses",
  "ties",
  "win_pct",
  "point_diff_per_game",
  "offensive_epa_per_play",
  "aggregated_at",
}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))

if not rows:
  raise SystemExit("team_week_outcomes.csv is empty")

missing = required - set(rows[0].keys())
if missing:
  raise SystemExit(f"team_week_outcomes.csv missing required columns: {sorted(missing)}")

seen = set()
for row in rows:
  team_id = row["team_id"].strip()
  season = row["nfl_season"].strip()
  week = row["nfl_week"].strip()
  if not team_id or not season or not week:
    raise SystemExit("team_week_outcomes.csv has empty team_id/nfl_season/nfl_week")

  key = (team_id, season, week)
  if key in seen:
    raise SystemExit(f"duplicate team-week key: {key}")
  seen.add(key)

  win_pct = float(row["win_pct"])
  if win_pct < 0 or win_pct > 1:
    raise SystemExit(f"win_pct out of range for {key}: {win_pct}")

print(f"validated team-week outcomes rows: {len(rows)}")
PY

echo "Data quality contract checks passed."
