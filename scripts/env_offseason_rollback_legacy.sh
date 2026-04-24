#!/usr/bin/env bash
set -euo pipefail

# Rollback profile for serving the legacy (pre-backfill-default) dataset.
# Source this file to bypass backfill bundle defaults with explicit legacy paths.

export OFFSEASON_REQUIRED_SEASONS="2026"

export MODEL_OUTPUTS_PATH="data/processed/model_outputs_hierarchical.csv"
export FALLBACK_OUTPUTS_PATH="data/processed/model_outputs.csv"
export PLAYER_DIMENSION_PATH="data/processed/player_dimension.csv"
export MOVEMENT_EVENTS_PATH="data/processed/movement_events.csv"
export TEAM_WEEK_FEATURES_PATH="data/processed/team_week_features.csv"

export HIERARCHICAL_EFFECTS_PATH="models/artifacts/hierarchical_effects.csv"
export BASELINE_COEFFICIENTS_PATH="models/artifacts/baseline_coefficients.csv"
