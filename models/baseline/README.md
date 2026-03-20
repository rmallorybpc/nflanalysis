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
