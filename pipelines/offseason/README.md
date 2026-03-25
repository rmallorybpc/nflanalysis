# Offseason One-Time Pipeline (2026)

This pipeline implements the authoritative offseason spec:

- 2026 offseason only
- no game-level team stats aggregation
- raw inputs:
  - data/raw/offseason/transactions_raw.csv
  - data/raw/offseason/players_metadata.csv
  - data/raw/offseason/team_spending_otc.csv
  - data/raw/offseason/win_totals.csv

## 1) Build canonical offseason tables

```bash
/usr/bin/python3 pipelines/offseason/ingest_offseason_snapshot.py \
  --transactions data/raw/offseason/transactions_raw.csv \
  --players data/raw/offseason/players_metadata.csv \
  --win-totals data/raw/offseason/win_totals.csv \
  --season 2026 \
  --week 1
```

Outputs:

- data/processed/offseason/movement_events.csv
- data/processed/offseason/player_dimension.csv
- data/processed/offseason/team_week_outcomes.csv
- data/processed/offseason/manual_review.csv

## 2) Build features with spending + win totals

```bash
/usr/bin/python3 pipelines/offseason/build_offseason_team_features.py \
  --movement data/processed/offseason/movement_events.csv \
  --players data/processed/offseason/player_dimension.csv \
  --outcomes data/processed/offseason/team_week_outcomes.csv \
  --team-spending data/raw/offseason/team_spending_otc.csv \
  --win-totals data/raw/offseason/win_totals.csv \
  --output data/processed/offseason/team_week_features.csv
```

## 3) Train models locally

```bash
/usr/bin/python3 models/baseline/train_baseline_model.py \
  --features data/processed/offseason/team_week_features.csv \
  --outcomes data/processed/offseason/team_week_outcomes.csv \
  --output data/processed/offseason/model_outputs.csv \
  --coefficients-output models/artifacts/offseason/baseline_coefficients.csv \
  --model-version baseline-ridge-v0.2.0-offseason
```

```bash
/usr/bin/python3 models/hierarchical/train_hierarchical_model.py \
  --features data/processed/offseason/team_week_features.csv \
  --outcomes data/processed/offseason/team_week_outcomes.csv \
  --movement data/processed/offseason/movement_events.csv \
  --players data/processed/offseason/player_dimension.csv \
  --output data/processed/offseason/model_outputs_hierarchical.csv \
  --effects-output models/artifacts/offseason/hierarchical_effects.csv \
  --model-version hierarchical-eb-v0.2.0-offseason
```

## Notes

- transaction type mapping:
  - Signed/Re-signed/Released/Waived/Claimed -> free_agency
  - Traded -> trade
  - Practice Squad/Reserve/Future -> ignored
- player_id is set to pfr_slug exactly.
- trade rows with unresolved from/to teams are written with blank team IDs and logged in data/processed/offseason/manual_review.csv.

## 4) Run local API against offseason outputs

```bash
MODEL_OUTPUTS_PATH=data/processed/offseason/model_outputs_hierarchical.csv \
FALLBACK_OUTPUTS_PATH=data/processed/offseason/model_outputs.csv \
HIERARCHICAL_EFFECTS_PATH=models/artifacts/offseason/hierarchical_effects.csv \
PLAYER_DIMENSION_PATH=data/processed/offseason/player_dimension.csv \
MOVEMENT_EVENTS_PATH=data/processed/offseason/movement_events.csv \
TEAM_WEEK_FEATURES_PATH=data/processed/offseason/team_week_features.csv \
/usr/bin/python3 -m api.app.main --host 0.0.0.0 --port 8080
```
