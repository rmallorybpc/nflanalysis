#!/usr/bin/env python3
"""Backfill offseason data and models across multiple seasons.

This orchestrator runs the existing offseason pipeline season-by-season using
snapshot-year aligned inputs, validates each slice, and then consolidates
successful slices into canonical offseason publish paths.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PLAYER_FIELDS = [
    "player_id",
    "full_name",
    "position_group",
    "position",
    "birth_date",
    "rookie_year",
    "experience_years",
    "active_status",
    "source",
    "normalized_at",
]

MOVEMENT_FIELDS = [
    "move_id",
    "event_date",
    "effective_date",
    "move_type",
    "player_id",
    "from_team_id",
    "to_team_id",
    "transaction_detail",
    "source",
    "nfl_season",
    "season_phase",
    "phase_week",
    "nfl_week",
    "ingested_at",
]

OUTCOME_FIELDS = [
    "team_id",
    "nfl_season",
    "nfl_week",
    "games_played",
    "wins",
    "losses",
    "ties",
    "win_pct",
    "point_diff_per_game",
    "offensive_epa_per_play",
    "aggregated_at",
]

FEATURE_FIELDS = [
    "team_id",
    "nfl_season",
    "nfl_week",
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
    "feature_version",
    "generated_at",
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


@dataclass
class SeasonPaths:
    season: int
    season_root: Path
    artifacts_root: Path
    movement: Path
    players: Path
    outcomes: Path
    review: Path
    features: Path
    model_outputs: Path
    model_outputs_hier: Path
    baseline_coefs: Path
    effects: Path


@dataclass
class SeasonResult:
    season: int
    ok: bool
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill offseason seasons and publish consolidated outputs")
    parser.add_argument("--start-season", type=int, default=2022)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--week", type=int, default=1)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed/offseason"))
    parser.add_argument("--artifacts-root", type=Path, default=Path("models/artifacts/offseason"))
    parser.add_argument(
        "--publish-dirname",
        default="",
        help="Optional subdirectory under processed/artifacts root for publish outputs",
    )
    parser.add_argument("--allow-partial-publish", action="store_true")
    parser.add_argument("--skip-publish-train", action="store_true")
    return parser.parse_args()


def run_cmd(cmd: list[str]) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_season_paths(processed_root: Path, artifacts_root: Path, season: int) -> SeasonPaths:
    season_root = processed_root / str(season)
    season_artifacts = artifacts_root / str(season)
    return SeasonPaths(
        season=season,
        season_root=season_root,
        artifacts_root=season_artifacts,
        movement=season_root / "movement_events.csv",
        players=season_root / "player_dimension.csv",
        outcomes=season_root / "team_week_outcomes.csv",
        review=season_root / "manual_review.csv",
        features=season_root / "team_week_features.csv",
        model_outputs=season_root / "model_outputs.csv",
        model_outputs_hier=season_root / "model_outputs_hierarchical.csv",
        baseline_coefs=season_artifacts / "baseline_coefficients.csv",
        effects=season_artifacts / "hierarchical_effects.csv",
    )


def require_non_empty(path: Path, label: str) -> list[dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"{label} is empty: {path}")
    return rows


def validate_single_season(path: Path, season: int, field: str = "nfl_season") -> None:
    rows = require_non_empty(path, path.name)
    seasons = {(row.get(field) or "").strip() for row in rows}
    seasons.discard("")
    expected = str(season)
    if seasons != {expected}:
        raise ValueError(f"season coherence failed for {path}: found {sorted(seasons)}, expected [{expected}]")


def validate_model_seasons(path: Path, expected_seasons: list[int]) -> None:
    rows = require_non_empty(path, path.name)
    seen = sorted({int((row.get("nfl_season") or "0").strip()) for row in rows if (row.get("nfl_season") or "").strip()})
    expected = sorted(expected_seasons)
    if seen != expected:
        raise ValueError(f"model outputs seasons mismatch for {path}: found {seen}, expected {expected}")


def run_season_pipeline(args: argparse.Namespace, season_paths: SeasonPaths) -> None:
    py = args.python

    run_cmd(
        [
            py,
            "pipelines/offseason/ingest_offseason_snapshot.py",
            "--snapshot-year",
            str(season_paths.season),
            "--season",
            str(season_paths.season),
            "--week",
            str(args.week),
            "--movement-output",
            str(season_paths.movement),
            "--players-output",
            str(season_paths.players),
            "--outcomes-output",
            str(season_paths.outcomes),
            "--review-output",
            str(season_paths.review),
        ]
    )

    movement_rows = read_csv(season_paths.movement)
    if not movement_rows:
        # Fallback: infer movement rows from players metadata for sparse transaction snapshots.
        players_snapshot = Path(f"data/raw/offseason/players_metadata_{season_paths.season}.csv")
        if not players_snapshot.exists():
            players_snapshot = Path("data/raw/offseason/players_metadata.csv")

        print(
            "[WARN] primary transaction ingest yielded zero movement rows; "
            f"retrying with inferred players metadata source: {players_snapshot}"
        )
        run_cmd(
            [
                py,
                "pipelines/offseason/ingest_offseason_snapshot.py",
                "--transactions",
                str(players_snapshot),
                "--snapshot-year",
                str(season_paths.season),
                "--season",
                str(season_paths.season),
                "--week",
                str(args.week),
                "--movement-output",
                str(season_paths.movement),
                "--players-output",
                str(season_paths.players),
                "--outcomes-output",
                str(season_paths.outcomes),
                "--review-output",
                str(season_paths.review),
            ]
        )

    run_cmd(
        [
            py,
            "pipelines/offseason/build_offseason_team_features.py",
            "--movement",
            str(season_paths.movement),
            "--players",
            str(season_paths.players),
            "--outcomes",
            str(season_paths.outcomes),
            "--snapshot-year",
            str(season_paths.season),
            "--output",
            str(season_paths.features),
        ]
    )

    run_cmd(
        [
            py,
            "models/baseline/train_baseline_model.py",
            "--features",
            str(season_paths.features),
            "--outcomes",
            str(season_paths.outcomes),
            "--output",
            str(season_paths.model_outputs),
            "--coefficients-output",
            str(season_paths.baseline_coefs),
            "--model-version",
            "baseline-ridge-v0.3.0-offseason-multiseason",
        ]
    )

    run_cmd(
        [
            py,
            "models/hierarchical/train_hierarchical_model.py",
            "--features",
            str(season_paths.features),
            "--outcomes",
            str(season_paths.outcomes),
            "--movement",
            str(season_paths.movement),
            "--players",
            str(season_paths.players),
            "--output",
            str(season_paths.model_outputs_hier),
            "--effects-output",
            str(season_paths.effects),
            "--model-version",
            "hierarchical-eb-v0.3.0-offseason-multiseason",
        ]
    )

    run_cmd(
        [
            py,
            "pipelines/offseason/validate_offseason_coverage.py",
            "--features",
            str(season_paths.features),
            "--outputs",
            str(season_paths.model_outputs_hier),
            "--season",
            str(season_paths.season),
            "--require-full",
        ]
    )

    require_non_empty(season_paths.movement, "movement_events")
    validate_single_season(season_paths.movement, season_paths.season)
    validate_single_season(season_paths.outcomes, season_paths.season)
    validate_single_season(season_paths.features, season_paths.season)
    validate_single_season(season_paths.model_outputs, season_paths.season)
    validate_single_season(season_paths.model_outputs_hier, season_paths.season)


def combine_rows(paths: list[Path], sort_key: tuple[str, ...]) -> list[dict[str, str]]:
    combined: list[dict[str, str]] = []
    for path in paths:
        combined.extend(read_csv(path))
    combined.sort(key=lambda row: tuple(row.get(k, "") for k in sort_key))
    return combined


def consolidate_publish(
    args: argparse.Namespace,
    successful_paths: list[SeasonPaths],
    publish_processed_root: Path,
    publish_artifacts_root: Path,
) -> None:
    players_by_id: dict[str, dict[str, str]] = {}
    for season_paths in successful_paths:
        for row in read_csv(season_paths.players):
            player_id = (row.get("player_id") or "").strip()
            if player_id:
                players_by_id[player_id] = row

    player_rows = sorted(players_by_id.values(), key=lambda row: row.get("player_id", ""))
    movement_rows = combine_rows([sp.movement for sp in successful_paths], ("nfl_season", "nfl_week", "move_id"))
    outcome_rows = combine_rows([sp.outcomes for sp in successful_paths], ("nfl_season", "nfl_week", "team_id"))
    feature_rows = combine_rows([sp.features for sp in successful_paths], ("nfl_season", "nfl_week", "team_id"))

    movement_out = publish_processed_root / "movement_events.csv"
    players_out = publish_processed_root / "player_dimension.csv"
    outcomes_out = publish_processed_root / "team_week_outcomes.csv"
    features_out = publish_processed_root / "team_week_features.csv"
    baseline_out = publish_processed_root / "model_outputs.csv"
    hierarchical_out = publish_processed_root / "model_outputs_hierarchical.csv"
    coefs_out = publish_artifacts_root / "baseline_coefficients.csv"
    effects_out = publish_artifacts_root / "hierarchical_effects.csv"

    write_csv(players_out, PLAYER_FIELDS, player_rows)
    write_csv(movement_out, MOVEMENT_FIELDS, movement_rows)
    write_csv(outcomes_out, OUTCOME_FIELDS, outcome_rows)
    write_csv(features_out, FEATURE_FIELDS, feature_rows)

    if args.skip_publish_train:
        print("[INFO] --skip-publish-train enabled: skipping consolidated model retrain")
        return

    run_cmd(
        [
            args.python,
            "models/baseline/train_baseline_model.py",
            "--features",
            str(features_out),
            "--outcomes",
            str(outcomes_out),
            "--output",
            str(baseline_out),
            "--coefficients-output",
            str(coefs_out),
            "--model-version",
            "baseline-ridge-v0.3.0-offseason-consolidated",
        ]
    )

    run_cmd(
        [
            args.python,
            "models/hierarchical/train_hierarchical_model.py",
            "--features",
            str(features_out),
            "--outcomes",
            str(outcomes_out),
            "--movement",
            str(movement_out),
            "--players",
            str(players_out),
            "--output",
            str(hierarchical_out),
            "--effects-output",
            str(effects_out),
            "--model-version",
            "hierarchical-eb-v0.3.0-offseason-consolidated",
        ]
    )


def summarize(results: list[SeasonResult]) -> None:
    print("\n=== Backfill Summary ===")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"season={result.season} status={status} message={result.message}")


def main() -> None:
    args = parse_args()

    if args.end_season < args.start_season:
        raise ValueError("end-season must be >= start-season")

    seasons = list(range(args.start_season, args.end_season + 1))
    results: list[SeasonResult] = []
    successful_paths: list[SeasonPaths] = []

    for season in seasons:
        season_paths = build_season_paths(args.processed_root, args.artifacts_root, season)
        try:
            run_season_pipeline(args, season_paths)
            results.append(SeasonResult(season=season, ok=True, message="validated"))
            successful_paths.append(season_paths)
        except Exception as exc:  # pragma: no cover - integration error surfacing
            results.append(SeasonResult(season=season, ok=False, message=str(exc)))
            print(f"[ERROR] season {season} failed: {exc}")

    summarize(results)

    failed = [r for r in results if not r.ok]
    if failed and not args.allow_partial_publish:
        raise SystemExit("one or more seasons failed; rerun with --allow-partial-publish to publish successful slices")

    if not successful_paths:
        raise SystemExit("no successful seasons available for consolidation")

    publish_processed_root = args.processed_root / args.publish_dirname if args.publish_dirname else args.processed_root
    publish_artifacts_root = args.artifacts_root / args.publish_dirname if args.publish_dirname else args.artifacts_root

    consolidate_publish(args, successful_paths, publish_processed_root, publish_artifacts_root)

    if args.skip_publish_train:
        print("[INFO] publish training skipped; no consolidated model validation run")
        raise SystemExit(1 if failed else 0)

    hierarchical_out = publish_processed_root / "model_outputs_hierarchical.csv"
    validate_model_seasons(hierarchical_out, [sp.season for sp in successful_paths])

    for season in [sp.season for sp in successful_paths]:
        run_cmd(
            [
                args.python,
                "pipelines/offseason/validate_offseason_coverage.py",
                "--features",
                str(publish_processed_root / "team_week_features.csv"),
                "--outputs",
                str(hierarchical_out),
                "--season",
                str(season),
                "--require-full",
            ]
        )

    if failed:
        raise SystemExit("published partial outputs: one or more requested seasons failed")


if __name__ == "__main__":
    main()
