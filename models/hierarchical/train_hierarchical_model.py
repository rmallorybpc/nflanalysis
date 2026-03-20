#!/usr/bin/env python3
"""Train a hierarchical player-position-team model with partial pooling.

This implementation uses a baseline ridge model as the fixed-effects component
and applies empirical-Bayes style shrinkage for movement-linked random effects.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from models.baseline.train_baseline_model import (  # pylint: disable=import-error
    COUNTERFACTUAL_ZERO_FEATURES,
    FEATURE_COLUMNS,
    MODEL_OUTPUT_FIELDS,
    OUTCOME_COLUMNS,
    build_design_matrix,
    build_training_rows,
    mean_std,
    predict,
    read_csv,
    ridge_fit,
    rmse,
    to_float,
    write_csv,
)

EFFECT_FIELDS = [
    "outcome_name",
    "effect_type",
    "effect_key",
    "raw_mean",
    "count",
    "shrunk_effect",
    "prior_strength",
    "trained_at",
]

POSITION_GROUP_FALLBACK = "other"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train hierarchical movement impact model")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/team_week_features.csv"),
        help="Feature table CSV",
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=Path("data/processed/team_week_outcomes.csv"),
        help="Outcome table CSV",
    )
    parser.add_argument(
        "--movement",
        type=Path,
        default=Path("data/processed/movement_events.csv"),
        help="Movement events CSV",
    )
    parser.add_argument(
        "--players",
        type=Path,
        default=Path("data/processed/player_dimension.csv"),
        help="Player dimension CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/model_outputs_hierarchical.csv"),
        help="Hierarchical model outputs CSV",
    )
    parser.add_argument(
        "--effects-output",
        type=Path,
        default=Path("models/artifacts/hierarchical_effects.csv"),
        help="Random effects artifact CSV",
    )
    parser.add_argument(
        "--model-version",
        type=str,
        default="hierarchical-eb-v0.1.0",
        help="Model version",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1.0,
        help="Ridge regularization for fixed-effects component",
    )
    parser.add_argument(
        "--prior-strength",
        type=float,
        default=3.0,
        help="Shrinkage prior strength k for empirical-Bayes effects",
    )
    return parser.parse_args()


def parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be integer-like, got {value}") from exc


def week_key(team_id: str, season: str, week: str) -> tuple[str, str, str]:
    return (team_id.strip(), season.strip(), week.strip())


def build_movement_exposures(
    movement_rows: list[dict[str, str]],
    player_rows: list[dict[str, str]],
) -> dict[tuple[str, str, str], list[tuple[str, str, float]]]:
    """Build signed movement exposure list by team-week.

    Each exposure tuple is (effect_type, effect_key, sign).
    """

    player_group = {
        r["player_id"].strip(): (r.get("position_group", "") or POSITION_GROUP_FALLBACK).strip().lower()
        for r in player_rows
    }

    exposures: dict[tuple[str, str, str], list[tuple[str, str, float]]] = defaultdict(list)

    for row in movement_rows:
        season = row.get("nfl_season", "").strip()
        week = row.get("nfl_week", "").strip()
        phase = row.get("season_phase", "").strip()
        if not season or not week or phase != "regular":
            continue

        player_id = row.get("player_id", "").strip()
        if not player_id:
            continue

        group = player_group.get(player_id, POSITION_GROUP_FALLBACK)
        if not group:
            group = POSITION_GROUP_FALLBACK

        to_team = row.get("to_team_id", "").strip()
        from_team = row.get("from_team_id", "").strip()
        if not to_team or not from_team:
            continue

        to_key = week_key(to_team, season, week)
        from_key = week_key(from_team, season, week)

        exposures[to_key].append(("player", player_id, 1.0))
        exposures[from_key].append(("player", player_id, -1.0))

        exposures[to_key].append(("position_team", f"{group}|{to_team}", 1.0))
        exposures[from_key].append(("position_team", f"{group}|{from_team}", -1.0))

    return exposures


def shrink_effect(sum_val: float, count: int, prior_strength: float) -> tuple[float, float]:
    if count <= 0:
        return (0.0, 0.0)
    raw_mean = sum_val / count
    weight = count / (count + prior_strength)
    return (raw_mean, raw_mean * weight)


def build_counterfactual_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for r in rows:
        cf = dict(r)
        for f in COUNTERFACTUAL_ZERO_FEATURES:
            cf[f] = "0"
        out.append(cf)
    return out


def main() -> None:
    args = parse_args()

    for path in (args.features, args.outcomes, args.movement, args.players):
        if not path.exists():
            raise FileNotFoundError(f"missing input file: {path}")

    feature_rows = read_csv(args.features)
    outcome_rows = read_csv(args.outcomes)
    movement_rows = read_csv(args.movement)
    player_rows = read_csv(args.players)

    rows = build_training_rows(feature_rows, outcome_rows)
    exposures = build_movement_exposures(movement_rows, player_rows)

    x_obs = build_design_matrix(rows, FEATURE_COLUMNS)
    cf_rows = build_counterfactual_rows(rows)
    x_cf = build_design_matrix(cf_rows, FEATURE_COLUMNS)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    data_version = f"features-{rows[0].get('feature_version', 'unknown')}"

    model_output_rows: list[dict[str, str]] = []
    effects_rows: list[dict[str, str]] = []

    for outcome in OUTCOME_COLUMNS:
        y = [to_float(r[outcome], outcome) for r in rows]
        beta = ridge_fit(x_obs, y, args.alpha)
        y_base_obs = predict(x_obs, beta)
        y_base_cf = predict(x_cf, beta)

        # Residuals from fixed-effects component.
        residuals = [a - p for a, p in zip(y, y_base_obs)]

        effect_sums: dict[tuple[str, str], float] = defaultdict(float)
        effect_counts: dict[tuple[str, str], int] = defaultdict(int)

        for i, row in enumerate(rows):
            key = week_key(row["team_id"], row["nfl_season"], row["nfl_week"])
            exps = exposures.get(key, [])
            if not exps:
                continue

            # Share residual across movement exposures at the same unit.
            denom = max(len(exps), 1)
            shared = residuals[i] / denom
            for effect_type, effect_key, sign in exps:
                effect_sums[(effect_type, effect_key)] += sign * shared
                effect_counts[(effect_type, effect_key)] += 1

        shrunk_effects: dict[tuple[str, str], float] = {}
        for k, s in effect_sums.items():
            c = effect_counts.get(k, 0)
            raw_mean, shrunk = shrink_effect(s, c, args.prior_strength)
            shrunk_effects[k] = shrunk
            effects_rows.append(
                {
                    "outcome_name": outcome,
                    "effect_type": k[0],
                    "effect_key": k[1],
                    "raw_mean": f"{raw_mean:.8f}",
                    "count": str(c),
                    "shrunk_effect": f"{shrunk:.8f}",
                    "prior_strength": f"{args.prior_strength:.4f}",
                    "trained_at": generated_at,
                }
            )

        y_h_obs: list[float] = []
        y_h_cf: list[float] = []

        for i, row in enumerate(rows):
            key = week_key(row["team_id"], row["nfl_season"], row["nfl_week"])
            exps = exposures.get(key, [])

            random_effect = 0.0
            for effect_type, effect_key, sign in exps:
                random_effect += sign * shrunk_effects.get((effect_type, effect_key), 0.0)

            # Observed includes random effects linked to movement exposures.
            obs_pred = y_base_obs[i] + random_effect
            # Counterfactual excludes movement-linked random effects.
            cf_pred = y_base_cf[i]

            y_h_obs.append(obs_pred)
            y_h_cf.append(cf_pred)

        mis = [o - c for o, c in zip(y_h_obs, y_h_cf)]
        mis_mu, mis_sigma = mean_std(mis)

        fit_err = rmse(y, y_h_obs)
        i50 = 0.674 * fit_err
        i90 = 1.645 * fit_err
        low_conf = (2 * i90) > (1.5 * fit_err)

        for i, row in enumerate(rows):
            if mis_sigma > 0:
                mis_z = (mis[i] - mis_mu) / mis_sigma
            else:
                mis_z = 0.0

            model_output_rows.append(
                {
                    "team_id": row["team_id"].strip(),
                    "nfl_season": row["nfl_season"].strip(),
                    "nfl_week": row["nfl_week"].strip(),
                    "outcome_name": outcome,
                    "observed_prediction": f"{y_h_obs[i]:.6f}",
                    "counterfactual_prediction": f"{y_h_cf[i]:.6f}",
                    "mis_value": f"{mis[i]:.6f}",
                    "mis_z": f"{mis_z:.6f}",
                    "interval_50_low": f"{(mis[i] - i50):.6f}",
                    "interval_50_high": f"{(mis[i] + i50):.6f}",
                    "interval_90_low": f"{(mis[i] - i90):.6f}",
                    "interval_90_high": f"{(mis[i] + i90):.6f}",
                    "low_confidence_flag": "true" if low_conf else "false",
                    "model_version": args.model_version,
                    "data_version": data_version,
                    "generated_at": generated_at,
                }
            )

    model_output_rows.sort(
        key=lambda r: (r["team_id"], r["nfl_season"], int(r["nfl_week"]), r["outcome_name"])
    )
    effects_rows.sort(key=lambda r: (r["outcome_name"], r["effect_type"], r["effect_key"]))

    write_csv(args.output, MODEL_OUTPUT_FIELDS, model_output_rows)
    write_csv(args.effects_output, EFFECT_FIELDS, effects_rows)

    print(
        f"Trained hierarchical model on {len(rows)} rows, wrote {len(model_output_rows)} "
        f"rows to {args.output} and {len(effects_rows)} effect rows to {args.effects_output}"
    )


if __name__ == "__main__":
    main()
