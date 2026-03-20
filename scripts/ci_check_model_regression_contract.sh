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

echo "Model regression contract checks passed."
