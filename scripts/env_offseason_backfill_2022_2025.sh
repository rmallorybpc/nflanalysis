#!/usr/bin/env bash
set -euo pipefail

# Deployment profile for serving the validated offseason backfill bundle.
# Source this file before starting API processes or release checks.

export OFFSEASON_SERVING_BUNDLE="data/processed/offseason/backfill_2022_2025"
export OFFSEASON_REQUIRED_SEASONS="2022,2023,2024,2025"

export MODEL_OUTPUTS_PATH="${OFFSEASON_SERVING_BUNDLE}/model_outputs_hierarchical.csv"
export FALLBACK_OUTPUTS_PATH="${OFFSEASON_SERVING_BUNDLE}/model_outputs.csv"
export PLAYER_DIMENSION_PATH="${OFFSEASON_SERVING_BUNDLE}/player_dimension.csv"
export MOVEMENT_EVENTS_PATH="${OFFSEASON_SERVING_BUNDLE}/movement_events.csv"
export TEAM_WEEK_FEATURES_PATH="${OFFSEASON_SERVING_BUNDLE}/team_week_features.csv"

export HIERARCHICAL_EFFECTS_PATH="models/artifacts/offseason/backfill_2022_2025/hierarchical_effects.csv"
export BASELINE_COEFFICIENTS_PATH="models/artifacts/offseason/backfill_2022_2025/baseline_coefficients.csv"
