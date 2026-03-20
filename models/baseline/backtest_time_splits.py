#!/usr/bin/env python3
"""Run time-based backtest splits for baseline ridge model."""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path

from train_baseline_model import (  # pylint: disable=import-error
    FEATURE_COLUMNS,
    OUTCOME_COLUMNS,
    build_design_matrix,
    build_training_rows,
    read_csv,
    ridge_fit,
    rmse,
    to_float,
    write_csv,
    predict,
)

SPLIT_FIELDS = [
    "team_id",
    "nfl_season",
    "nfl_week",
    "time_index",
    "split",
    "generated_at",
]

METRIC_FIELDS = [
    "outcome_name",
    "split",
    "rmse",
    "mae",
    "n_rows",
    "model_version",
    "generated_at",
]

PREDICTION_FIELDS = [
    "team_id",
    "nfl_season",
    "nfl_week",
    "split",
    "outcome_name",
    "actual",
    "predicted",
    "error",
    "generated_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline model time-based backtest")
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
        "--splits-output",
        type=Path,
        default=Path("data/processed/backtest_splits.csv"),
        help="Output split assignment CSV",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=Path("models/artifacts/backtest_metrics.csv"),
        help="Output metrics CSV",
    )
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=Path("models/artifacts/backtest_predictions.csv"),
        help="Output predictions CSV",
    )
    parser.add_argument(
        "--model-version",
        type=str,
        default="baseline-ridge-v0.1.0-backtest",
        help="Model version label for backtest artifacts",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1.0,
        help="Ridge regularization strength",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.6,
        help="Proportion of time index used for train split",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.2,
        help="Proportion of time index used for validation split",
    )
    return parser.parse_args()


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["team_id"].strip(), row["nfl_season"].strip(), row["nfl_week"].strip())


def time_index_key(row: dict[str, str]) -> tuple[int, int]:
    return (int(row["nfl_season"].strip()), int(row["nfl_week"].strip()))


def assign_time_splits(rows: list[dict[str, str]], train_ratio: float, val_ratio: float):
    ordered_row_keys = sorted(
        {row_key(r) for r in rows},
        key=lambda k: (int(k[1]), int(k[2]), k[0]),
    )
    if len(ordered_row_keys) < 3:
        raise ValueError("need at least 3 chronological rows for train/val/test split")

    n = len(ordered_row_keys)
    train_end = max(1, int(n * train_ratio))
    val_end = max(train_end + 1, int(n * (train_ratio + val_ratio)))
    if val_end >= n:
        val_end = n - 1

    split_lookup: dict[tuple[str, str, str], str] = {}
    for i, key in enumerate(ordered_row_keys):
        if i < train_end:
            split_lookup[key] = "train"
        elif i < val_end:
            split_lookup[key] = "validation"
        else:
            split_lookup[key] = "test"

    time_points = sorted({(int(k[1]), int(k[2])) for k in ordered_row_keys})
    return split_lookup, time_points


def mae(y_true: list[float], y_pred: list[float]) -> float:
    if not y_true:
        return 0.0
    return sum(abs(a - b) for a, b in zip(y_true, y_pred)) / len(y_true)


def build_metric_row(
    outcome_name: str,
    split_name: str,
    y_true: list[float],
    y_pred: list[float],
    model_version: str,
    generated_at: str,
) -> dict[str, str]:
    return {
        "outcome_name": outcome_name,
        "split": split_name,
        "rmse": f"{rmse(y_true, y_pred):.6f}",
        "mae": f"{mae(y_true, y_pred):.6f}",
        "n_rows": str(len(y_true)),
        "model_version": model_version,
        "generated_at": generated_at,
    }


def main() -> None:
    args = parse_args()

    if not args.features.exists():
        raise FileNotFoundError(f"missing features file: {args.features}")
    if not args.outcomes.exists():
        raise FileNotFoundError(f"missing outcomes file: {args.outcomes}")

    feature_rows = read_csv(args.features)
    outcome_rows = read_csv(args.outcomes)
    rows = build_training_rows(feature_rows, outcome_rows)

    split_lookup, ordered_time_keys = assign_time_splits(rows, args.train_ratio, args.val_ratio)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    split_rows: list[dict[str, str]] = []
    for row in rows:
        tk = time_index_key(row)
        key = row_key(row)
        split_rows.append(
            {
                "team_id": row["team_id"].strip(),
                "nfl_season": row["nfl_season"].strip(),
                "nfl_week": row["nfl_week"].strip(),
                "time_index": f"{tk[0]}-{tk[1]:02d}",
                "split": split_lookup[key],
                "generated_at": generated_at,
            }
        )

    split_by_key = {row_key(r): r["split"] for r in split_rows}

    train_rows = [r for r in rows if split_by_key[row_key(r)] == "train"]
    val_rows = [r for r in rows if split_by_key[row_key(r)] == "validation"]
    test_rows = [r for r in rows if split_by_key[row_key(r)] == "test"]

    if not train_rows or not val_rows or not test_rows:
        raise ValueError("split configuration produced empty train/validation/test partition")

    x_train = build_design_matrix(train_rows, FEATURE_COLUMNS)
    x_val = build_design_matrix(val_rows, FEATURE_COLUMNS)
    x_test = build_design_matrix(test_rows, FEATURE_COLUMNS)

    metric_rows: list[dict[str, str]] = []
    prediction_rows: list[dict[str, str]] = []

    for outcome in OUTCOME_COLUMNS:
        y_train = [to_float(r[outcome], outcome) for r in train_rows]
        y_val = [to_float(r[outcome], outcome) for r in val_rows]
        y_test = [to_float(r[outcome], outcome) for r in test_rows]

        beta = ridge_fit(x_train, y_train, args.alpha)
        p_train = predict(x_train, beta)
        p_val = predict(x_val, beta)
        p_test = predict(x_test, beta)

        metric_rows.append(build_metric_row(outcome, "train", y_train, p_train, args.model_version, generated_at))
        metric_rows.append(build_metric_row(outcome, "validation", y_val, p_val, args.model_version, generated_at))
        metric_rows.append(build_metric_row(outcome, "test", y_test, p_test, args.model_version, generated_at))

        for subset_name, subset_rows, y_true, y_pred in (
            ("train", train_rows, y_train, p_train),
            ("validation", val_rows, y_val, p_val),
            ("test", test_rows, y_test, p_test),
        ):
            for row, a, p in zip(subset_rows, y_true, y_pred):
                prediction_rows.append(
                    {
                        "team_id": row["team_id"].strip(),
                        "nfl_season": row["nfl_season"].strip(),
                        "nfl_week": row["nfl_week"].strip(),
                        "split": subset_name,
                        "outcome_name": outcome,
                        "actual": f"{a:.6f}",
                        "predicted": f"{p:.6f}",
                        "error": f"{(a - p):.6f}",
                        "generated_at": generated_at,
                    }
                )

    split_rows.sort(key=lambda r: (r["nfl_season"], int(r["nfl_week"]), r["team_id"]))
    metric_rows.sort(key=lambda r: (r["outcome_name"], r["split"]))
    prediction_rows.sort(
        key=lambda r: (r["outcome_name"], r["split"], r["nfl_season"], int(r["nfl_week"]), r["team_id"])
    )

    write_csv(args.splits_output, SPLIT_FIELDS, split_rows)
    write_csv(args.metrics_output, METRIC_FIELDS, metric_rows)
    write_csv(args.predictions_output, PREDICTION_FIELDS, prediction_rows)

    print(
        f"Backtest complete across {len(ordered_time_keys)} time points: "
        f"train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}; "
        f"wrote splits={args.splits_output}, metrics={args.metrics_output}, predictions={args.predictions_output}"
    )


if __name__ == "__main__":
    main()
