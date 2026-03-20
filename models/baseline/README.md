# Baseline Model

## Issue #11: Regularized Baseline Regression

Train baseline ridge-style regression for MVP outcomes:

```bash
/usr/bin/python3 models/baseline/train_baseline_model.py \
  --features data/processed/team_week_features.csv \
  --outcomes data/processed/team_week_outcomes.csv \
  --output data/processed/model_outputs.csv \
  --coefficients-output models/artifacts/baseline_coefficients.csv \
  --model-version baseline-ridge-v0.1.0 \
  --alpha 1.0
```

Outputs:

- data/processed/model_outputs.csv
- models/artifacts/baseline_coefficients.csv

Outcomes modeled:

- win_pct
- point_diff_per_game
- offensive_epa_per_play

Counterfactual logic:

- Sets movement-driven feature columns to zero while preserving schedule strength.
- MIS is computed as observed_prediction - counterfactual_prediction.

## Issue #12: Time-Based Backtest Split Framework

Run chronological train/validation/test backtest splits and evaluate metrics:

```bash
/usr/bin/python3 models/baseline/backtest_time_splits.py \
  --features data/processed/team_week_features.csv \
  --outcomes data/processed/team_week_outcomes.csv \
  --splits-output data/processed/backtest_splits.csv \
  --metrics-output models/artifacts/backtest_metrics.csv \
  --predictions-output models/artifacts/backtest_predictions.csv \
  --model-version baseline-ridge-v0.1.0-backtest \
  --alpha 1.0 \
  --train-ratio 0.6 \
  --val-ratio 0.2
```

Backtest outputs:

- data/processed/backtest_splits.csv
- models/artifacts/backtest_metrics.csv
- models/artifacts/backtest_predictions.csv
