#!/usr/bin/env python3
"""Run pre-trend and placebo validation tests for movement impact estimates."""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

SUMMARY_FIELDS = [
    "test_name",
    "outcome_name",
    "statistic_name",
    "statistic_value",
    "n_units",
    "notes",
    "generated_at",
]

DETAIL_FIELDS = [
    "test_name",
    "team_id",
    "nfl_season",
    "nfl_week",
    "outcome_name",
    "value",
    "generated_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate pre-trend and placebo diagnostics")
    parser.add_argument(
        "--movement",
        type=Path,
        default=Path("data/processed/movement_events.csv"),
        help="Movement events CSV",
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=Path("data/processed/team_week_outcomes.csv"),
        help="Team-week outcomes CSV",
    )
    parser.add_argument(
        "--model-outputs",
        type=Path,
        default=Path("data/processed/model_outputs.csv"),
        help="Model outputs CSV",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("models/artifacts/pretrend_placebo_summary.csv"),
        help="Summary artifact output",
    )
    parser.add_argument(
        "--detail-output",
        type=Path,
        default=Path("models/artifacts/pretrend_placebo_details.csv"),
        help="Detail artifact output",
    )
    parser.add_argument(
        "--pretrend-lookback",
        type=int,
        default=2,
        help="Number of prior weeks required for pre-trend slope",
    )
    parser.add_argument(
        "--placebo-iterations",
        type=int,
        default=200,
        help="Number of placebo randomizations",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be integer-like, got {value}") from exc


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def pretrend_slope(values: list[float]) -> float:
    # Simple linear slope across equally spaced points indexed 1..n.
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(1, n + 1))
    x_bar = mean([float(x) for x in xs])
    y_bar = mean(values)
    num = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, values))
    den = sum((x - x_bar) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def main() -> None:
    args = parse_args()

    for path in (args.movement, args.outcomes, args.model_outputs):
        if not path.exists():
            raise FileNotFoundError(f"missing input file: {path}")

    movement_rows = read_csv(args.movement)
    outcome_rows = read_csv(args.outcomes)
    model_rows = read_csv(args.model_outputs)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    outcome_by_key = {
        (r["team_id"].strip(), r["nfl_season"].strip(), to_int(r["nfl_week"], "nfl_week")): r
        for r in outcome_rows
    }

    team_week_outcomes: dict[tuple[str, str], dict[int, dict[str, str]]] = defaultdict(dict)
    for r in outcome_rows:
        team = r["team_id"].strip()
        season = r["nfl_season"].strip()
        week = to_int(r["nfl_week"], "nfl_week")
        team_week_outcomes[(team, season)][week] = r

    model_by_key_outcome: dict[tuple[str, str, int, str], float] = {}
    for r in model_rows:
        key = (
            r["team_id"].strip(),
            r["nfl_season"].strip(),
            to_int(r["nfl_week"], "nfl_week"),
            r["outcome_name"].strip(),
        )
        model_by_key_outcome[key] = abs(to_float(r["mis_value"], "mis_value"))

    movement_regular = []
    for r in movement_rows:
        week = r["nfl_week"].strip()
        if not week:
            continue
        if r["season_phase"].strip() != "regular":
            continue
        movement_regular.append(
            {
                "move_id": r["move_id"].strip(),
                "season": r["nfl_season"].strip(),
                "week": to_int(week, "nfl_week"),
                "to_team": r["to_team_id"].strip(),
                "from_team": r["from_team_id"].strip(),
            }
        )

    summary_rows: list[dict[str, str]] = []
    detail_rows: list[dict[str, str]] = []

    # Pre-trend: slope of previous lookback weeks' outcomes before movement week.
    for outcome_name in ("win_pct", "point_diff_per_game", "offensive_epa_per_play"):
        slopes: list[float] = []
        for ev in movement_regular:
            for team in (ev["to_team"], ev["from_team"]):
                weekly = team_week_outcomes.get((team, ev["season"]), {})
                prior_vals = []
                for w in range(ev["week"] - args.pretrend_lookback, ev["week"]):
                    row = weekly.get(w)
                    if row is None:
                        prior_vals = []
                        break
                    prior_vals.append(to_float(row[outcome_name], outcome_name))
                if len(prior_vals) == args.pretrend_lookback:
                    slope = pretrend_slope(prior_vals)
                    slopes.append(slope)
                    detail_rows.append(
                        {
                            "test_name": "pretrend",
                            "team_id": team,
                            "nfl_season": ev["season"],
                            "nfl_week": str(ev["week"]),
                            "outcome_name": outcome_name,
                            "value": f"{slope:.6f}",
                            "generated_at": generated_at,
                        }
                    )

        summary_rows.append(
            {
                "test_name": "pretrend",
                "outcome_name": outcome_name,
                "statistic_name": "mean_pretrend_slope",
                "statistic_value": f"{mean(slopes):.6f}",
                "n_units": str(len(slopes)),
                "notes": "lower absolute slope suggests better pre-trend balance",
                "generated_at": generated_at,
            }
        )

    # Placebo: compare actual treated mean |MIS| to randomized team-week assignment.
    random.seed(args.seed)
    all_keys = {(r["team_id"].strip(), r["nfl_season"].strip(), to_int(r["nfl_week"], "nfl_week")) for r in outcome_rows}

    treated_keys = set()
    for ev in movement_regular:
        treated_keys.add((ev["to_team"], ev["season"], ev["week"]))
        treated_keys.add((ev["from_team"], ev["season"], ev["week"]))

    n_treated = len(treated_keys)
    key_list = sorted(all_keys)

    for outcome_name in ("win_pct", "point_diff_per_game", "offensive_epa_per_play"):
        actual_vals = [
            model_by_key_outcome[(t, s, w, outcome_name)]
            for (t, s, w) in treated_keys
            if (t, s, w, outcome_name) in model_by_key_outcome
        ]
        actual_mean = mean(actual_vals)

        placebo_means = []
        if n_treated > 0 and len(key_list) >= n_treated:
            for _ in range(args.placebo_iterations):
                sampled = random.sample(key_list, n_treated)
                vals = [
                    model_by_key_outcome[(t, s, w, outcome_name)]
                    for (t, s, w) in sampled
                    if (t, s, w, outcome_name) in model_by_key_outcome
                ]
                placebo_means.append(mean(vals))

        extreme = sum(1 for v in placebo_means if v >= actual_mean)
        p_value = (extreme + 1) / (len(placebo_means) + 1) if placebo_means else 1.0

        summary_rows.append(
            {
                "test_name": "placebo",
                "outcome_name": outcome_name,
                "statistic_name": "one_sided_p_value",
                "statistic_value": f"{p_value:.6f}",
                "n_units": str(len(placebo_means)),
                "notes": "fraction of placebo means >= actual treated mean |MIS|",
                "generated_at": generated_at,
            }
        )
        summary_rows.append(
            {
                "test_name": "placebo",
                "outcome_name": outcome_name,
                "statistic_name": "actual_treated_mean_abs_mis",
                "statistic_value": f"{actual_mean:.6f}",
                "n_units": str(len(actual_vals)),
                "notes": "reference value used against placebo distribution",
                "generated_at": generated_at,
            }
        )

        detail_rows.append(
            {
                "test_name": "placebo",
                "team_id": "ALL",
                "nfl_season": "ALL",
                "nfl_week": "ALL",
                "outcome_name": outcome_name,
                "value": f"{actual_mean:.6f}",
                "generated_at": generated_at,
            }
        )

    write_csv(args.summary_output, SUMMARY_FIELDS, summary_rows)
    write_csv(args.detail_output, DETAIL_FIELDS, detail_rows)

    print(
        f"Validation complete: wrote summary={args.summary_output} ({len(summary_rows)} rows), "
        f"details={args.detail_output} ({len(detail_rows)} rows)"
    )


if __name__ == "__main__":
    main()
