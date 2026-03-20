#!/usr/bin/env bash
set -euo pipefail

echo "Running model regression contract checks..."

if [[ ! -f docs/modeling-notes.md ]]; then
  echo "Missing docs/modeling-notes.md"
  exit 1
fi

if [[ ! -d models/artifacts ]]; then
  echo "Missing models/artifacts directory"
  exit 1
fi

if [[ ! -f models/baseline/train_baseline_model.py ]]; then
  echo "Missing models/baseline/train_baseline_model.py"
  exit 1
fi

if [[ ! -f models/baseline/backtest_time_splits.py ]]; then
  echo "Missing models/baseline/backtest_time_splits.py"
  exit 1
fi

if [[ ! -f models/baseline/validate_pretrend_placebo.py ]]; then
  echo "Missing models/baseline/validate_pretrend_placebo.py"
  exit 1
fi

if [[ ! -f models/hierarchical/train_hierarchical_model.py ]]; then
  echo "Missing models/hierarchical/train_hierarchical_model.py"
  exit 1
fi

if [[ ! -f api/app/counterfactual_service.py ]]; then
  echo "Missing api/app/counterfactual_service.py"
  exit 1
fi

if [[ ! -f api/app/main.py ]]; then
  echo "Missing api/app/main.py"
  exit 1
fi

if [[ ! -f api/tests/test_counterfactual_service.py ]]; then
  echo "Missing api/tests/test_counterfactual_service.py"
  exit 1
fi

if [[ ! -f dashboard/src/index.html ]]; then
  echo "Missing dashboard/src/index.html"
  exit 1
fi

if [[ ! -f dashboard/src/styles.css ]]; then
  echo "Missing dashboard/src/styles.css"
  exit 1
fi

if [[ ! -f dashboard/src/overview.js ]]; then
  echo "Missing dashboard/src/overview.js"
  exit 1
fi

if [[ ! -f dashboard/src/team.html ]]; then
  echo "Missing dashboard/src/team.html"
  exit 1
fi

if [[ ! -f dashboard/src/team.css ]]; then
  echo "Missing dashboard/src/team.css"
  exit 1
fi

if [[ ! -f dashboard/src/team.js ]]; then
  echo "Missing dashboard/src/team.js"
  exit 1
fi

if [[ ! -f dashboard/src/scenario.html ]]; then
  echo "Missing dashboard/src/scenario.html"
  exit 1
fi

if [[ ! -f dashboard/src/scenario.css ]]; then
  echo "Missing dashboard/src/scenario.css"
  exit 1
fi

if [[ ! -f dashboard/src/scenario.js ]]; then
  echo "Missing dashboard/src/scenario.js"
  exit 1
fi

if [[ ! -f dashboard/public/overview.sample.json ]]; then
  echo "Missing dashboard/public/overview.sample.json"
  exit 1
fi

if [[ ! -f dashboard/public/team-detail.sample.json ]]; then
  echo "Missing dashboard/public/team-detail.sample.json"
  exit 1
fi

if [[ ! -f dashboard/public/scenario-sandbox.sample.json ]]; then
  echo "Missing dashboard/public/scenario-sandbox.sample.json"
  exit 1
fi

if [[ ! -f dashboard/tests/test_overview_payload.py ]]; then
  echo "Missing dashboard/tests/test_overview_payload.py"
  exit 1
fi

if [[ ! -f dashboard/tests/test_team_detail_payload.py ]]; then
  echo "Missing dashboard/tests/test_team_detail_payload.py"
  exit 1
fi

if [[ ! -f dashboard/tests/test_scenario_sandbox_payload.py ]]; then
  echo "Missing dashboard/tests/test_scenario_sandbox_payload.py"
  exit 1
fi

if [[ ! -f api/schemas/movement-impact.schema.json ]]; then
  echo "Missing api/schemas/movement-impact.schema.json"
  exit 1
fi

if [[ ! -f api/schemas/overview-dashboard.schema.json ]]; then
  echo "Missing api/schemas/overview-dashboard.schema.json"
  exit 1
fi

if [[ ! -f api/schemas/team-detail.schema.json ]]; then
  echo "Missing api/schemas/team-detail.schema.json"
  exit 1
fi

if [[ ! -f api/schemas/scenario-sandbox.schema.json ]]; then
  echo "Missing api/schemas/scenario-sandbox.schema.json"
  exit 1
fi

if [[ ! -f data/processed/model_outputs.csv ]]; then
  echo "Missing data/processed/model_outputs.csv"
  exit 1
fi

if [[ ! -f models/artifacts/baseline_coefficients.csv ]]; then
  echo "Missing models/artifacts/baseline_coefficients.csv"
  exit 1
fi

if [[ ! -f data/processed/backtest_splits.csv ]]; then
  echo "Missing data/processed/backtest_splits.csv"
  exit 1
fi

if [[ ! -f models/artifacts/backtest_metrics.csv ]]; then
  echo "Missing models/artifacts/backtest_metrics.csv"
  exit 1
fi

if [[ ! -f models/artifacts/backtest_predictions.csv ]]; then
  echo "Missing models/artifacts/backtest_predictions.csv"
  exit 1
fi

if [[ ! -f models/artifacts/pretrend_placebo_summary.csv ]]; then
  echo "Missing models/artifacts/pretrend_placebo_summary.csv"
  exit 1
fi

if [[ ! -f models/artifacts/pretrend_placebo_details.csv ]]; then
  echo "Missing models/artifacts/pretrend_placebo_details.csv"
  exit 1
fi

if [[ ! -f data/processed/model_outputs_hierarchical.csv ]]; then
  echo "Missing data/processed/model_outputs_hierarchical.csv"
  exit 1
fi

if [[ ! -f models/artifacts/hierarchical_effects.csv ]]; then
  echo "Missing models/artifacts/hierarchical_effects.csv"
  exit 1
fi

grep -qi "hierarchical" docs/modeling-notes.md || {
  echo "modeling-notes.md should mention hierarchical modeling plan"
  exit 1
}

python3 - <<'PY'
import csv

path = "data/processed/model_outputs.csv"
required = {
    "team_id",
    "nfl_season",
    "nfl_week",
    "outcome_name",
    "observed_prediction",
    "counterfactual_prediction",
    "mis_value",
    "mis_z",
    "interval_50_low",
    "interval_50_high",
    "interval_90_low",
    "interval_90_high",
    "low_confidence_flag",
    "model_version",
    "data_version",
    "generated_at",
}

with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("model_outputs.csv is empty")

missing = required - set(rows[0].keys())
if missing:
    raise SystemExit(f"model_outputs.csv missing columns: {sorted(missing)}")

allowed_outcomes = {"win_pct", "point_diff_per_game", "offensive_epa_per_play"}
allowed_flag = {"true", "false"}

for row in rows:
    outcome = row["outcome_name"].strip()
    if outcome not in allowed_outcomes:
        raise SystemExit(f"invalid outcome_name in model_outputs.csv: {outcome}")
    flag = row["low_confidence_flag"].strip().lower()
    if flag not in allowed_flag:
        raise SystemExit(f"invalid low_confidence_flag in model_outputs.csv: {flag}")

print(f"validated model outputs rows: {len(rows)}")
PY

python3 - <<'PY'
import csv

split_path = "data/processed/backtest_splits.csv"
metric_path = "models/artifacts/backtest_metrics.csv"

with open(split_path, newline="", encoding="utf-8") as f:
  split_rows = list(csv.DictReader(f))
if not split_rows:
  raise SystemExit("backtest_splits.csv is empty")

allowed_splits = {"train", "validation", "test"}
split_values = {r["split"].strip() for r in split_rows}
if not allowed_splits.issubset(split_values):
  raise SystemExit(f"backtest_splits.csv missing split labels: expected {allowed_splits}, got {split_values}")

with open(metric_path, newline="", encoding="utf-8") as f:
  metric_rows = list(csv.DictReader(f))
if not metric_rows:
  raise SystemExit("backtest_metrics.csv is empty")

required_metric_cols = {"outcome_name", "split", "rmse", "mae", "n_rows", "model_version", "generated_at"}
missing = required_metric_cols - set(metric_rows[0].keys())
if missing:
  raise SystemExit(f"backtest_metrics.csv missing columns: {sorted(missing)}")

for row in metric_rows:
  if row["split"].strip() not in allowed_splits:
    raise SystemExit(f"invalid split in backtest_metrics.csv: {row['split']}")
  if int(row["n_rows"]) <= 0:
    raise SystemExit("backtest_metrics.csv contains non-positive n_rows")

print(f"validated backtest artifacts: splits={len(split_rows)} metrics={len(metric_rows)}")
PY

python3 - <<'PY'
import csv

summary_path = "models/artifacts/pretrend_placebo_summary.csv"
detail_path = "models/artifacts/pretrend_placebo_details.csv"

with open(summary_path, newline="", encoding="utf-8") as f:
  summary_rows = list(csv.DictReader(f))
if not summary_rows:
  raise SystemExit("pretrend_placebo_summary.csv is empty")

required_summary = {"test_name", "outcome_name", "statistic_name", "statistic_value", "n_units", "notes", "generated_at"}
missing = required_summary - set(summary_rows[0].keys())
if missing:
  raise SystemExit(f"pretrend_placebo_summary.csv missing columns: {sorted(missing)}")

test_names = {r["test_name"].strip() for r in summary_rows}
if not {"pretrend", "placebo"}.issubset(test_names):
  raise SystemExit(f"pretrend_placebo_summary.csv missing test groups: {test_names}")

with open(detail_path, newline="", encoding="utf-8") as f:
  detail_rows = list(csv.DictReader(f))
if not detail_rows:
  raise SystemExit("pretrend_placebo_details.csv is empty")

required_detail = {"test_name", "team_id", "nfl_season", "nfl_week", "outcome_name", "value", "generated_at"}
missing = required_detail - set(detail_rows[0].keys())
if missing:
  raise SystemExit(f"pretrend_placebo_details.csv missing columns: {sorted(missing)}")

print(f"validated pretrend/placebo artifacts: summary={len(summary_rows)} details={len(detail_rows)}")
PY

python3 - <<'PY'
import csv

path = "data/processed/model_outputs_hierarchical.csv"
required = {
  "team_id",
  "nfl_season",
  "nfl_week",
  "outcome_name",
  "observed_prediction",
  "counterfactual_prediction",
  "mis_value",
  "mis_z",
  "interval_50_low",
  "interval_50_high",
  "interval_90_low",
  "interval_90_high",
  "low_confidence_flag",
  "model_version",
  "data_version",
  "generated_at",
}

with open(path, newline="", encoding="utf-8") as f:
  rows = list(csv.DictReader(f))
if not rows:
  raise SystemExit("model_outputs_hierarchical.csv is empty")

missing = required - set(rows[0].keys())
if missing:
  raise SystemExit(f"model_outputs_hierarchical.csv missing columns: {sorted(missing)}")

allowed_outcomes = {"win_pct", "point_diff_per_game", "offensive_epa_per_play"}
for row in rows:
  if row["outcome_name"].strip() not in allowed_outcomes:
    raise SystemExit(f"invalid outcome_name in model_outputs_hierarchical.csv: {row['outcome_name']}")

effects_path = "models/artifacts/hierarchical_effects.csv"
with open(effects_path, newline="", encoding="utf-8") as f:
  effect_rows = list(csv.DictReader(f))
if not effect_rows:
  raise SystemExit("hierarchical_effects.csv is empty")

required_effect = {
  "outcome_name",
  "effect_type",
  "effect_key",
  "raw_mean",
  "count",
  "shrunk_effect",
  "prior_strength",
  "trained_at",
}
missing = required_effect - set(effect_rows[0].keys())
if missing:
  raise SystemExit(f"hierarchical_effects.csv missing columns: {sorted(missing)}")

print(f"validated hierarchical artifacts: outputs={len(rows)} effects={len(effect_rows)}")
PY

python3 - <<'PY'
import json
from pathlib import Path

schema_paths = [
  Path("api/schemas/movement-impact.schema.json"),
  Path("api/schemas/overview-dashboard.schema.json"),
  Path("api/schemas/team-detail.schema.json"),
  Path("api/schemas/scenario-sandbox.schema.json"),
]

for path in schema_paths:
  with path.open(encoding="utf-8") as f:
    payload = json.load(f)
  required_top_level = {"$schema", "$id", "title", "type", "properties"}
  missing = required_top_level - set(payload.keys())
  if missing:
    raise SystemExit(f"{path} missing top-level fields: {sorted(missing)}")
  if payload.get("type") != "object":
    raise SystemExit(f"{path} must have top-level type=object")

print(f"validated api schema files: {len(schema_paths)}")
PY

python3 -m unittest api.tests.test_counterfactual_service
python3 -m unittest dashboard.tests.test_overview_payload
python3 -m unittest dashboard.tests.test_team_detail_payload
python3 -m unittest dashboard.tests.test_scenario_sandbox_payload

chmod +x scripts/ci_check_dashboard_contracts.sh
./scripts/ci_check_dashboard_contracts.sh

echo "Model regression contract checks passed."
