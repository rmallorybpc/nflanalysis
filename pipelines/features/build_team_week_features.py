#!/usr/bin/env python3
"""Build canonical team-week feature table from processed inputs."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


CANONICAL_FIELDS = [
    "team_id",
    "nfl_season",
    "nfl_week",
    "roster_churn_rate",
    "inbound_move_count",
    "outbound_move_count",
    "position_value_delta",
    "schedule_strength_index",
    "feature_version",
    "generated_at",
]

POSITION_WEIGHTS = {
    "QB": 4.0,
    "WR": 2.5,
    "TE": 1.8,
    "RB": 1.6,
    "LT": 2.2,
    "RT": 2.0,
    "LG": 1.8,
    "RG": 1.8,
    "C": 1.9,
    "EDGE": 3.0,
    "DE": 2.6,
    "DT": 2.3,
    "LB": 2.1,
    "CB": 2.7,
    "S": 2.2,
    "K": 0.7,
    "P": 0.6,
    "LS": 0.4,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build team-week feature table")
    parser.add_argument(
        "--movement",
        type=Path,
        default=Path("data/processed/movement_events.csv"),
        help="Canonical movement events CSV",
    )
    parser.add_argument(
        "--players",
        type=Path,
        default=Path("data/processed/player_dimension.csv"),
        help="Canonical player dimension CSV",
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=Path("data/processed/team_week_outcomes.csv"),
        help="Canonical team-week outcomes CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/team_week_features.csv"),
        help="Output team-week features CSV",
    )
    parser.add_argument(
        "--feature-version",
        type=str,
        default="0.1.0",
        help="Semantic version for feature set",
    )
    parser.add_argument(
        "--roster-size",
        type=float,
        default=53.0,
        help="Roster baseline denominator for churn rate",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace output instead of upserting existing rows",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_existing(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    if not path.exists():
        return {}
    rows = read_csv(path)
    by_key: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["team_id"], row["nfl_season"], row["nfl_week"])
        by_key[key] = row
    return by_key


def write_output(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def position_weight(position: str) -> float:
    pos = position.strip().upper()
    if pos in POSITION_WEIGHTS:
        return POSITION_WEIGHTS[pos]
    return 1.0


def build_features(
    movement_rows: list[dict[str, str]],
    player_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
    feature_version: str,
    roster_size: float,
    generated_at: str,
) -> dict[tuple[str, str, str], dict[str, str]]:
    player_position = {r["player_id"].strip(): r["position"].strip().upper() for r in player_rows}

    inbound_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    outbound_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    value_delta: dict[tuple[str, str, str], float] = defaultdict(float)

    for row in movement_rows:
        season = row["nfl_season"].strip()
        week = row["nfl_week"].strip()
        if not week:
            continue

        player_id = row["player_id"].strip()
        weight = position_weight(player_position.get(player_id, ""))

        to_key = (row["to_team_id"].strip(), season, week)
        from_key = (row["from_team_id"].strip(), season, week)

        inbound_counts[to_key] += 1
        outbound_counts[from_key] += 1
        value_delta[to_key] += weight
        value_delta[from_key] -= weight

    features: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in outcome_rows:
        key = (row["team_id"].strip(), row["nfl_season"].strip(), row["nfl_week"].strip())
        inbound = inbound_counts.get(key, 0)
        outbound = outbound_counts.get(key, 0)
        churn = (inbound + outbound) / roster_size if roster_size > 0 else 0.0

        features[key] = {
            "team_id": key[0],
            "nfl_season": key[1],
            "nfl_week": key[2],
            "roster_churn_rate": f"{churn:.6f}",
            "inbound_move_count": str(inbound),
            "outbound_move_count": str(outbound),
            "position_value_delta": f"{value_delta.get(key, 0.0):.4f}",
            "schedule_strength_index": f"{0.0:.4f}",
            "feature_version": feature_version,
            "generated_at": generated_at,
        }

    return features


def main() -> None:
    args = parse_args()

    for path in (args.movement, args.players, args.outcomes):
        if not path.exists():
            raise FileNotFoundError(f"missing input file: {path}")

    movement_rows = read_csv(args.movement)
    player_rows = read_csv(args.players)
    outcome_rows = read_csv(args.outcomes)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    incoming = build_features(
        movement_rows,
        player_rows,
        outcome_rows,
        feature_version=args.feature_version,
        roster_size=args.roster_size,
        generated_at=generated_at,
    )

    if args.replace:
        merged = incoming
    else:
        merged = read_existing(args.output)
        merged.update(incoming)

    sorted_rows = [merged[k] for k in sorted(merged.keys())]
    write_output(sorted_rows, args.output)

    print(
        f"Built {len(incoming)} team-week feature rows; "
        f"output has {len(sorted_rows)} rows at {args.output}"
    )


if __name__ == "__main__":
    main()
