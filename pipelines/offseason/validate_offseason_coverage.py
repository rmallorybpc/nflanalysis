from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

NFL_TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LV",
    "LAC",
    "LAR",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate offseason output coverage")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("data/processed/offseason/team_week_features.csv"),
        help="Path to offseason feature table",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=Path("data/processed/offseason/model_outputs_hierarchical.csv"),
        help="Path to offseason model outputs",
    )
    parser.add_argument("--season", type=int, default=2026, help="Season to validate")
    parser.add_argument(
        "--require-full",
        action="store_true",
        help="Exit non-zero if fewer than 32 teams are present",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def teams_for_season(rows: list[dict[str, str]], season: int) -> set[str]:
    season_str = str(season)
    teams: set[str] = set()
    for row in rows:
        if row.get("nfl_season", "").strip() != season_str:
            continue
        team_id = row.get("team_id", "").strip()
        if team_id:
            teams.add(team_id)
    return teams


def main() -> None:
    args = parse_args()

    feature_rows = read_rows(args.features)
    output_rows = read_rows(args.outputs)

    feature_teams = teams_for_season(feature_rows, args.season)
    output_teams = teams_for_season(output_rows, args.season)

    expected = set(NFL_TEAMS)
    present = feature_teams & output_teams
    missing = sorted(expected - present)
    extra = sorted(present - expected)

    print(f"season={args.season}")
    print(f"feature_teams={len(feature_teams)} model_teams={len(output_teams)} overlap={len(present)}")
    print(f"present_teams={sorted(present)}")
    print(f"missing_teams={missing}")
    if extra:
        print(f"unexpected_teams={extra}")

    if args.require_full and len(present) < len(expected):
        print("coverage validation failed: expected all 32 teams", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
