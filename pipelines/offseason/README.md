# Offseason One-Time Pipeline (Year-Aware)

This pipeline implements the authoritative offseason spec and supports year-suffixed raw snapshots:

- 2026 default, with optional `--snapshot-year` input switching
- no game-level team stats aggregation
- raw inputs:
  - data/raw/offseason/transactions_raw.csv
  - data/raw/offseason/players_metadata.csv
  - data/raw/offseason/team_spending_otc.csv
  - data/raw/offseason/win_totals.csv

## 1) Build canonical offseason tables

```bash
/usr/bin/python3 pipelines/offseason/ingest_offseason_snapshot.py \
  --snapshot-year 2025 \
  --season 2026 \
  --week 1
```

When `--snapshot-year` is set and raw paths are left at defaults, the script automatically prefers:

- `data/raw/offseason/transactions_raw_YYYY.csv`
- `data/raw/offseason/players_metadata_YYYY.csv`
- `data/raw/offseason/win_totals_YYYY.csv`

If those files do not exist, it falls back to the non-suffixed defaults.

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
  --snapshot-year 2025 \
  --output data/processed/offseason/team_week_features.csv
```

When `--snapshot-year` is set and raw paths are left at defaults, this script automatically prefers:

- `data/raw/offseason/team_spending_otc_YYYY.csv`
- `data/raw/offseason/win_totals_YYYY.csv`

If those files do not exist, it falls back to the non-suffixed defaults.

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
- player_id is `pfr_slug` when present; otherwise derive `nfl:{profile-slug}` from NFL profile source URL.
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

## 5) Validate full-team coverage (32 teams)

```bash
/usr/bin/python3 pipelines/offseason/validate_offseason_coverage.py \
  --features data/processed/offseason/team_week_features.csv \
  --outputs data/processed/offseason/model_outputs_hierarchical.csv \
  --season 2026 \
  --require-full
```

## 6) Backfill 2022-2025 And Publish Consolidated Outputs

Run the multi-season orchestrator to build isolated per-season artifacts,
validate each season, then publish consolidated outputs:

```bash
/usr/bin/python3 pipelines/offseason/backfill_multi_season.py \
  --start-season 2022 \
  --end-season 2025
```

What this does:

- Writes per-season intermediate outputs under:
  - `data/processed/offseason/<season>/...`
  - `models/artifacts/offseason/<season>/...`
- Runs per-season gates:
  - non-empty movement events
  - season label coherence across movement/outcomes/features/model outputs
  - full 32-team coverage check
- Publishes consolidated canonical files under:
  - `data/processed/offseason/`
  - `models/artifacts/offseason/`

Optional flags:

- `--allow-partial-publish`: publish successful seasons even if some requested seasons fail.
- `--skip-publish-train`: skip consolidated model retraining (writes combined features/outcomes/movement/players only).
- `--publish-dirname <name>`: publish consolidated files to `data/processed/offseason/<name>/` and `models/artifacts/offseason/<name>/`.

## 7) Promote Bundle To API Runtime Checks

Run API smoke checks against the consolidated serving bundle:

```bash
OFFSEASON_SERVING_BUNDLE=data/processed/offseason/backfill_2022_2025 \
bash scripts/ci_check_api_season_smoke.sh
```

The check validates:

- Overview, team-detail, and scenario-sandbox payload generation for seasons 2022-2025.
- Unsupported season handling remains strict.

`scripts/run_final.sh` includes this smoke check in its required gate sequence.
