#!/usr/bin/env bash
set -euo pipefail

echo "Running data quality contract checks..."

required_paths=(
  "docs/data-dictionary.md"
  "docs/metric-spec.md"
  "api/schemas/movement-impact.schema.json"
  "data/external/nfl_calendar_mapping.csv"
  "data/external/position_value_weights.csv"
  "data/processed/movement_events.csv"
  "data/processed/player_dimension.csv"
  "data/processed/team_week_outcomes.csv"
  "data/processed/team_week_features.csv"
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

for section in nfl_calendar_mapping movement_events player_dimension team_week_outcomes team_week_features model_outputs; do
  grep -q "## ${section}" docs/data-dictionary.md || {
    echo "data-dictionary.md missing section: ${section}"
    exit 1
  }
done

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

python3 - <<'PY'
import csv

path = "data/processed/team_week_features.csv"
required = {
  "team_id",
  "nfl_season",
  "nfl_week",
  "roster_churn_rate",
  "inbound_move_count",
  "outbound_move_count",
  "offense_skill_value_delta",
  "offense_line_value_delta",
  "defense_front_value_delta",
  "defense_second_level_value_delta",
  "defense_secondary_value_delta",
  "special_teams_value_delta",
  "other_value_delta",
  "position_value_delta",
  "schedule_strength_index",
  "feature_version",
  "generated_at",
}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))

if not rows:
  raise SystemExit("team_week_features.csv is empty")

missing = required - set(rows[0].keys())
if missing:
  raise SystemExit(f"team_week_features.csv missing required columns: {sorted(missing)}")

seen = set()
for row in rows:
  team_id = row["team_id"].strip()
  season = row["nfl_season"].strip()
  week = row["nfl_week"].strip()
  if not team_id or not season or not week:
    raise SystemExit("team_week_features.csv has empty team_id/nfl_season/nfl_week")

  key = (team_id, season, week)
  if key in seen:
    raise SystemExit(f"duplicate feature key: {key}")
  seen.add(key)

  churn = float(row["roster_churn_rate"])
  inbound = int(row["inbound_move_count"])
  outbound = int(row["outbound_move_count"])
  total_delta = float(row["position_value_delta"])
  group_sum = (
    float(row["offense_skill_value_delta"]) +
    float(row["offense_line_value_delta"]) +
    float(row["defense_front_value_delta"]) +
    float(row["defense_second_level_value_delta"]) +
    float(row["defense_secondary_value_delta"]) +
    float(row["special_teams_value_delta"]) +
    float(row["other_value_delta"])
  )
  if churn < 0:
    raise SystemExit(f"negative roster_churn_rate for key={key}")
  if inbound < 0 or outbound < 0:
    raise SystemExit(f"negative move count for key={key}")
  if abs(group_sum - total_delta) > 0.0002:
    raise SystemExit(f"position group deltas do not sum to position_value_delta for key={key}")

  schedule_strength = float(row["schedule_strength_index"])
  if schedule_strength < -1.0 or schedule_strength > 1.0:
    raise SystemExit(f"schedule_strength_index out of range [-1,1] for key={key}")

print(f"validated team-week feature rows: {len(rows)}")
PY

python3 - <<'PY'
import csv


def read_rows(path: str):
  with open(path, newline="", encoding="utf-8") as f:
    return list(csv.DictReader(f))


calendar_rows = read_rows("data/external/nfl_calendar_mapping.csv")
movement_rows = read_rows("data/processed/movement_events.csv")
player_rows = read_rows("data/processed/player_dimension.csv")
team_week_rows = read_rows("data/processed/team_week_outcomes.csv")
feature_rows = read_rows("data/processed/team_week_features.csv")

calendar_by_date = {r["calendar_date"]: r for r in calendar_rows}
player_ids = {r["player_id"].strip() for r in player_rows}

if "" in player_ids:
  raise SystemExit("player_dimension.csv contains blank player_id")

for row in movement_rows:
  move_id = row["move_id"].strip()
  player_id = row["player_id"].strip()
  effective_date = row["effective_date"].strip()

  if player_id not in player_ids:
    raise SystemExit(f"movement_events player_id missing in player_dimension: {move_id} -> {player_id}")

  cal = calendar_by_date.get(effective_date)
  if cal is None:
    raise SystemExit(f"movement_events effective_date missing in calendar: {move_id} -> {effective_date}")

  if row["nfl_season"].strip() != cal["nfl_season"].strip():
    raise SystemExit(f"movement_events nfl_season mismatch calendar for move_id={move_id}")

  if row["season_phase"].strip() != cal["season_phase"].strip():
    raise SystemExit(f"movement_events season_phase mismatch calendar for move_id={move_id}")

  if row["nfl_week"].strip() != cal["nfl_week"].strip():
    raise SystemExit(f"movement_events nfl_week mismatch calendar for move_id={move_id}")

for row in team_week_rows:
  key = (row["team_id"].strip(), row["nfl_season"].strip(), row["nfl_week"].strip())
  games_played = int(row["games_played"].strip())
  wins = int(row["wins"].strip())
  losses = int(row["losses"].strip())
  ties = int(row["ties"].strip())

  if wins + losses + ties != games_played:
    raise SystemExit(f"team_week_outcomes W/L/T sum mismatch for key={key}")

feature_keys = {(r["team_id"].strip(), r["nfl_season"].strip(), r["nfl_week"].strip()) for r in feature_rows}
outcome_keys = {(r["team_id"].strip(), r["nfl_season"].strip(), r["nfl_week"].strip()) for r in team_week_rows}

if feature_keys != outcome_keys:
  missing = sorted(outcome_keys - feature_keys)
  extra = sorted(feature_keys - outcome_keys)
  raise SystemExit(
    f"team_week_features keys mismatch outcomes; missing={missing[:3]} extra={extra[:3]}"
  )

all_zero_schedule = True
for row in feature_rows:
  if abs(float(row["schedule_strength_index"].strip())) > 0.000001:
    all_zero_schedule = False
    break

if all_zero_schedule:
  raise SystemExit("team_week_features schedule_strength_index is all zero; check Issue #10 logic")

print("validated cross-table consistency checks")
PY

python3 - <<'PY'
import csv
from collections import defaultdict
from pathlib import Path


def read_rows(path: str):
  with open(path, newline="", encoding="utf-8") as f:
    return list(csv.DictReader(f))


# Rule 1: enforce a unique destination team per (player_id, nfl_season)
# on non-inferred (verified) movement rows.
movement_path = "data/processed/movement_events.csv"
movement_rows = read_rows(movement_path)
destinations = defaultdict(set)

for row in movement_rows:
  move_id = row.get("move_id", "").strip()
  if move_id.startswith("ofs_"):
    continue
  player_id = row.get("player_id", "").strip()
  season = row.get("nfl_season", "").strip()
  to_team_id = row.get("to_team_id", "").strip()
  if player_id and season and to_team_id:
    destinations[(player_id, season)].add(to_team_id)

for (player_id, season), teams in sorted(destinations.items()):
  if len(teams) > 1:
    ordered = sorted(teams)
    print(
      f"CONFLICT: player {player_id} has multiple destination teams in season {season}: "
      f"{ordered[0]}, {ordered[1]}"
    )
    raise SystemExit(1)


# Rule 2: warn on potentially unverified rookie/draft entries across offseason metadata files.
for metadata_path in sorted(Path("data/raw/offseason").glob("players_metadata_*.csv")):
  season = metadata_path.stem.rsplit("_", 1)[-1]
  rows = read_rows(str(metadata_path))
  for row in rows:
    experience = row.get("experience", "").strip()
    draft_year = row.get("draft_year", "").strip()
    if experience == "0" and (not draft_year or draft_year == season):
      player = row.get("player", "").strip() or "<unknown>"
      team = row.get("team", "").strip() or "<unknown>"
      print(
        f"WARN: unverified rookie/draft entry: {player} team={team} "
        f"season={season} — verify against authoritative draft results"
      )


# Rule 3: warn if inferred fallback movement entries exceed 50% for any season.
cols = set(movement_rows[0].keys()) if movement_rows else set()
if movement_rows and "ingested_at" in cols and "move_id" in cols and "nfl_season" in cols:
  season_total = defaultdict(int)
  season_inferred = defaultdict(int)

  for row in movement_rows:
    season = row.get("nfl_season", "").strip()
    if not season:
      continue
    season_total[season] += 1
    move_id = row.get("move_id", "").strip()
    ingested_at = row.get("ingested_at", "").strip()
    if ingested_at and move_id.startswith("ofs_"):
      season_inferred[season] += 1

  for season in sorted(season_total.keys()):
    total = season_total[season]
    if total == 0:
      continue
    inferred = season_inferred[season]
    pct = inferred * 100.0 / total
    if pct > 50.0:
      print(
        f"WARN: season {season} has {pct:.1f}% inferred movement events "
        f"— consider reviewing against authoritative transaction source"
      )

print("validated semantic movement checks")
PY

echo "Data quality contract checks passed."
