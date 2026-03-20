#!/usr/bin/env python3
"""Train a baseline ridge regression model and emit canonical model outputs."""

from __future__ import annotations

import argparse
import csv
import math
from datetime import UTC, datetime
from pathlib import Path

FEATURE_COLUMNS = [
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
]

COUNTERFACTUAL_ZERO_FEATURES = [
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
]

OUTCOME_COLUMNS = [
    "win_pct",
    "point_diff_per_game",
    "offensive_epa_per_play",
]

MODEL_OUTPUT_FIELDS = [
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
]

COEFFICIENT_FIELDS = [
    "outcome_name",
    "feature_name",
    "coefficient",
    "alpha",
    "n_rows",
    "trained_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train baseline ridge model")
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
        "--output",
        type=Path,
        default=Path("data/processed/model_outputs.csv"),
        help="Model outputs CSV",
    )
    parser.add_argument(
        "--coefficients-output",
        type=Path,
        default=Path("models/artifacts/baseline_coefficients.csv"),
        help="Model coefficients CSV",
    )
    parser.add_argument(
        "--model-version",
        type=str,
        default="baseline-ridge-v0.1.0",
        help="Model version tag",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1.0,
        help="Ridge regularization strength",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def transpose(m: list[list[float]]) -> list[list[float]]:
    return [list(row) for row in zip(*m)]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    rows = len(a)
    cols = len(b[0])
    inner = len(b)
    out = [[0.0 for _ in range(cols)] for _ in range(rows)]
    for i in range(rows):
        for k in range(inner):
            aik = a[i][k]
            for j in range(cols):
                out[i][j] += aik * b[k][j]
    return out


def invert_matrix(m: list[list[float]]) -> list[list[float]]:
    n = len(m)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]

    for col in range(n):
        pivot = col
        for r in range(col + 1, n):
            if abs(aug[r][col]) > abs(aug[pivot][col]):
                pivot = r
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("matrix is singular")
        aug[col], aug[pivot] = aug[pivot], aug[col]

        pivot_val = aug[col][col]
        for j in range(2 * n):
            aug[col][j] /= pivot_val

        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            for j in range(2 * n):
                aug[r][j] -= factor * aug[col][j]

    return [row[n:] for row in aug]


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def build_training_rows(
    feature_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    outcomes_by_key = {
        (r["team_id"].strip(), r["nfl_season"].strip(), r["nfl_week"].strip()): r
        for r in outcome_rows
    }

    rows = []
    for fr in feature_rows:
        key = (fr["team_id"].strip(), fr["nfl_season"].strip(), fr["nfl_week"].strip())
        if key not in outcomes_by_key:
            continue
        row = {**fr, **outcomes_by_key[key]}
        rows.append(row)

    if not rows:
        raise ValueError("no overlapping rows between features and outcomes")
    return rows


def build_design_matrix(rows: list[dict[str, str]], features: list[str]) -> list[list[float]]:
    x = []
    for row in rows:
        x.append([to_float(row[f], f) for f in features])
    return x


def ridge_fit(x: list[list[float]], y: list[float], alpha: float) -> list[float]:
    x_i = [[1.0] + row for row in x]
    xt = transpose(x_i)
    xtx = matmul(xt, x_i)

    for i in range(len(xtx)):
        if i == 0:
            continue
        xtx[i][i] += alpha

    xty = matmul(xt, [[v] for v in y])
    inv = invert_matrix(xtx)
    beta_col = matmul(inv, xty)
    return [r[0] for r in beta_col]


def predict(x: list[list[float]], beta: list[float]) -> list[float]:
    preds = []
    for row in x:
        y_hat = beta[0]
        for i, val in enumerate(row):
            y_hat += beta[i + 1] * val
        preds.append(y_hat)
    return preds


def rmse(y_true: list[float], y_pred: list[float]) -> float:
    if not y_true:
        return 0.0
    mse = sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / len(y_true)
    return math.sqrt(mse)


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    mu = sum(values) / len(values)
    var = sum((v - mu) ** 2 for v in values) / len(values)
    return (mu, math.sqrt(var))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    args = parse_args()

    if not args.features.exists():
        raise FileNotFoundError(f"missing features file: {args.features}")
    if not args.outcomes.exists():
        raise FileNotFoundError(f"missing outcomes file: {args.outcomes}")

    feature_rows = read_csv(args.features)
    outcome_rows = read_csv(args.outcomes)
    rows = build_training_rows(feature_rows, outcome_rows)

    x_obs = build_design_matrix(rows, FEATURE_COLUMNS)
    counterfactual_features = []
    for r in rows:
        cf = dict(r)
        for f in COUNTERFACTUAL_ZERO_FEATURES:
            cf[f] = "0"
        counterfactual_features.append(cf)
    x_cf = build_design_matrix(counterfactual_features, FEATURE_COLUMNS)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    data_version = f"features-{rows[0].get('feature_version', 'unknown')}"

    model_output_rows: list[dict[str, str]] = []
    coefficient_rows: list[dict[str, str]] = []

    for outcome in OUTCOME_COLUMNS:
        y = [to_float(r[outcome], outcome) for r in rows]
        beta = ridge_fit(x_obs, y, args.alpha)
        y_obs = predict(x_obs, beta)
        y_cf = predict(x_cf, beta)
        mis = [o - c for o, c in zip(y_obs, y_cf)]
        mis_mu, mis_sigma = mean_std(mis)

        err = rmse(y, y_obs)
        i50 = 0.674 * err
        i90 = 1.645 * err
        low_conf = (2 * i90) > (1.5 * err)

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
                    "observed_prediction": f"{y_obs[i]:.6f}",
                    "counterfactual_prediction": f"{y_cf[i]:.6f}",
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

        coefficient_rows.append(
            {
                "outcome_name": outcome,
                "feature_name": "intercept",
                "coefficient": f"{beta[0]:.8f}",
                "alpha": f"{args.alpha:.4f}",
                "n_rows": str(len(rows)),
                "trained_at": generated_at,
            }
        )
        for idx, feature_name in enumerate(FEATURE_COLUMNS):
            coefficient_rows.append(
                {
                    "outcome_name": outcome,
                    "feature_name": feature_name,
                    "coefficient": f"{beta[idx + 1]:.8f}",
                    "alpha": f"{args.alpha:.4f}",
                    "n_rows": str(len(rows)),
                    "trained_at": generated_at,
                }
            )

    model_output_rows.sort(
        key=lambda r: (r["team_id"], r["nfl_season"], int(r["nfl_week"]), r["outcome_name"])
    )

    write_csv(args.output, MODEL_OUTPUT_FIELDS, model_output_rows)
    write_csv(args.coefficients_output, COEFFICIENT_FIELDS, coefficient_rows)

    print(
        f"Trained baseline model on {len(rows)} rows, wrote {len(model_output_rows)} "
        f"model output rows to {args.output} and coefficients to {args.coefficients_output}"
    )


if __name__ == "__main__":
    main()
