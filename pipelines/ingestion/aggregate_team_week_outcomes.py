#!/usr/bin/env python3
"""Aggregate team-game source rows into canonical team-week outcomes table."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


REQUIRED_SOURCE_FIELDS = {
    "game_id",
    "game_date",
    "team_id",
    "opponent_team_id",
    "points_for",
    "points_against",
    "offensive_epa_per_play",
}

CANONICAL_FIELDS = [
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


@dataclass(frozen=True)
class CalendarRow:
    nfl_season: str
    season_phase: str
    nfl_week: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate team-week outcomes")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/team_game_stats_source.csv"),
        help="Raw team game-level source CSV",
    )
    parser.add_argument(
        "--calendar",
        type=Path,
        default=Path("data/external/nfl_calendar_mapping.csv"),
        help="Calendar mapping CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/team_week_outcomes.csv"),
        help="Canonical team-week output CSV",
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


def read_calendar(path: Path) -> dict[str, CalendarRow]:
    rows = read_csv(path)
    mapping: dict[str, CalendarRow] = {}
    for row in rows:
        mapping[row["calendar_date"]] = CalendarRow(
            nfl_season=row["nfl_season"],
            season_phase=row["season_phase"],
            nfl_week=row["nfl_week"],
        )
    return mapping


def validate_source_headers(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("source file has no rows")

    missing = REQUIRED_SOURCE_FIELDS - set(rows[0].keys())
    if missing:
        raise ValueError(f"source file missing required columns: {sorted(missing)}")


def to_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be integer, got {value}") from exc


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def ensure_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value}") from exc


def outcome_flags(points_for: int, points_against: int) -> tuple[int, int, int]:
    if points_for > points_against:
        return (1, 0, 0)
    if points_for < points_against:
        return (0, 1, 0)
    return (0, 0, 1)


def aggregate(
    source_rows: list[dict[str, str]], calendar: dict[str, CalendarRow], aggregated_at: str
) -> dict[tuple[str, str, str], dict[str, str]]:
    buckets: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {
            "games_played": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "ties": 0.0,
            "point_diff_total": 0.0,
            "off_epa_total": 0.0,
        }
    )

    for raw in source_rows:
        game_date = ensure_date(raw["game_date"].strip(), "game_date")
        if game_date not in calendar:
            raise ValueError(f"game_date {game_date} not found in calendar mapping")

        cal = calendar[game_date]
        if cal.season_phase != "regular" or not cal.nfl_week:
            continue

        team_id = raw["team_id"].strip()
        if not team_id:
            raise ValueError("team_id cannot be empty")

        points_for = to_int(raw["points_for"].strip(), "points_for")
        points_against = to_int(raw["points_against"].strip(), "points_against")
        off_epa = to_float(raw["offensive_epa_per_play"].strip(), "offensive_epa_per_play")

        wins, losses, ties = outcome_flags(points_for, points_against)
        key = (team_id, cal.nfl_season, cal.nfl_week)
        bucket = buckets[key]
        bucket["games_played"] += 1
        bucket["wins"] += wins
        bucket["losses"] += losses
        bucket["ties"] += ties
        bucket["point_diff_total"] += (points_for - points_against)
        bucket["off_epa_total"] += off_epa

    results: dict[tuple[str, str, str], dict[str, str]] = {}
    for key, bucket in buckets.items():
        team_id, nfl_season, nfl_week = key
        games_played = int(bucket["games_played"])
        wins = int(bucket["wins"])
        losses = int(bucket["losses"])
        ties = int(bucket["ties"])

        win_pct = (wins + 0.5 * ties) / games_played if games_played else 0.0
        point_diff_per_game = bucket["point_diff_total"] / games_played if games_played else 0.0
        off_epa_per_play = bucket["off_epa_total"] / games_played if games_played else 0.0

        results[key] = {
            "team_id": team_id,
            "nfl_season": nfl_season,
            "nfl_week": nfl_week,
            "games_played": str(games_played),
            "wins": str(wins),
            "losses": str(losses),
            "ties": str(ties),
            "win_pct": f"{win_pct:.4f}",
            "point_diff_per_game": f"{point_diff_per_game:.4f}",
            "offensive_epa_per_play": f"{off_epa_per_play:.4f}",
            "aggregated_at": aggregated_at,
        }

    return results


def read_existing(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    if not path.exists():
        return {}

    rows = read_csv(path)
    existing: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["team_id"], row["nfl_season"], row["nfl_week"])
        existing[key] = row
    return existing


def write_output(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    if not args.source.exists():
        raise FileNotFoundError(f"missing source file: {args.source}")
    if not args.calendar.exists():
        raise FileNotFoundError(f"missing calendar file: {args.calendar}")

    source_rows = read_csv(args.source)
    validate_source_headers(source_rows)
    calendar = read_calendar(args.calendar)

    aggregated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    incoming = aggregate(source_rows, calendar, aggregated_at)

    if args.replace:
        merged = incoming
    else:
        merged = read_existing(args.output)
        merged.update(incoming)

    sorted_rows = [merged[key] for key in sorted(merged.keys())]
    write_output(sorted_rows, args.output)

    print(
        f"Aggregated {len(source_rows)} source rows into {len(incoming)} team-week rows; "
        f"output has {len(sorted_rows)} rows at {args.output}"
    )


if __name__ == "__main__":
    main()
