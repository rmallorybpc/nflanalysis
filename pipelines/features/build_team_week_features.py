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

POSITION_GROUPS = [
    "offense_skill",
    "offense_line",
    "defense_front",
    "defense_second_level",
    "defense_secondary",
    "special_teams",
    "other",
]


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
        "--position-weights",
        type=Path,
        default=Path("data/external/position_value_weights.csv"),
        help="CSV mapping position to weight",
    )
    parser.add_argument(
        "--team-games",
        type=Path,
        default=Path("data/raw/team_game_stats_source.csv"),
        help="Raw team game-level source CSV for opponent mapping",
    )
    parser.add_argument(
        "--calendar",
        type=Path,
        default=Path("data/external/nfl_calendar_mapping.csv"),
        help="Calendar mapping CSV for date to season/week",
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


def load_position_weights(path: Path) -> dict[str, float]:
    if not path.exists():
        return dict(POSITION_WEIGHTS)

    rows = read_csv(path)
    weights = dict(POSITION_WEIGHTS)
    for row in rows:
        pos = row.get("position", "").strip().upper()
        weight_raw = row.get("weight", "").strip()
        if not pos or not weight_raw:
            continue
        try:
            weights[pos] = float(weight_raw)
        except ValueError as exc:
            raise ValueError(f"invalid weight for position {pos}: {weight_raw}") from exc

    return weights


def read_calendar_lookup(path: Path) -> dict[str, tuple[str, str, str]]:
    rows = read_csv(path)
    lookup: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        lookup[row["calendar_date"]] = (
            row["nfl_season"].strip(),
            row["nfl_week"].strip(),
            row["season_phase"].strip(),
        )
    return lookup


def parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be integer-like, got {value}") from exc


def build_opponent_strength_history(
    outcome_rows: list[dict[str, str]],
) -> dict[tuple[str, str], list[tuple[int, float, int]]]:
    history: dict[tuple[str, str], list[tuple[int, float, int]]] = defaultdict(list)
    for row in outcome_rows:
        team = row["team_id"].strip()
        season = row["nfl_season"].strip()
        week = parse_int(row["nfl_week"].strip(), "nfl_week")
        win_pct = float(row["win_pct"].strip())
        games = parse_int(row["games_played"].strip(), "games_played")
        history[(team, season)].append((week, win_pct, games))

    for key in history:
        history[key].sort(key=lambda t: t[0])

    return history


def prior_win_pct(
    history: dict[tuple[str, str], list[tuple[int, float, int]]],
    opponent_team_id: str,
    season: str,
    week: int,
) -> float:
    rows = history.get((opponent_team_id, season), [])
    total_w = 0.0
    total_games = 0
    same_week_total_w = 0.0
    same_week_games = 0
    for wk, pct, games in rows:
        if wk < week:
            total_w += pct * games
            total_games += games
        elif wk == week:
            same_week_total_w += pct * games
            same_week_games += games
        elif wk > week:
            break

    if total_games == 0:
        if same_week_games > 0:
            return same_week_total_w / same_week_games
        return 0.5
    return total_w / total_games


def build_opponents_by_key(
    team_game_rows: list[dict[str, str]],
    calendar_lookup: dict[str, tuple[str, str, str]],
) -> dict[tuple[str, str, str], list[str]]:
    opponents: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for row in team_game_rows:
        game_date = row.get("game_date", "").strip()
        if game_date not in calendar_lookup:
            continue

        season, week, phase = calendar_lookup[game_date]
        if phase != "regular" or not week:
            continue

        team_id = row.get("team_id", "").strip()
        opponent_team_id = row.get("opponent_team_id", "").strip()
        if not team_id or not opponent_team_id:
            continue

        key = (team_id, season, week)
        opponents[key].append(opponent_team_id)

    return opponents


def build_features(
    movement_rows: list[dict[str, str]],
    player_rows: list[dict[str, str]],
    team_game_rows: list[dict[str, str]],
    calendar_lookup: dict[str, tuple[str, str, str]],
    outcome_rows: list[dict[str, str]],
    position_weights: dict[str, float],
    feature_version: str,
    roster_size: float,
    generated_at: str,
) -> dict[tuple[str, str, str], dict[str, str]]:
    player_position = {r["player_id"].strip(): r["position"].strip().upper() for r in player_rows}
    player_group = {r["player_id"].strip(): r["position_group"].strip().lower() for r in player_rows}

    inbound_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    outbound_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    value_delta: dict[tuple[str, str, str], float] = defaultdict(float)
    group_delta: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    opponents_by_key = build_opponents_by_key(team_game_rows, calendar_lookup)
    opponent_history = build_opponent_strength_history(outcome_rows)

    for row in movement_rows:
        season = row["nfl_season"].strip()
        week = row["nfl_week"].strip()
        if not week:
            continue

        player_id = row["player_id"].strip()
        pos = player_position.get(player_id, "")
        weight = position_weights.get(pos, position_weight(pos))
        group = player_group.get(player_id, "other")
        if group not in POSITION_GROUPS:
            group = "other"

        to_key = (row["to_team_id"].strip(), season, week)
        from_key = (row["from_team_id"].strip(), season, week)

        inbound_counts[to_key] += 1
        outbound_counts[from_key] += 1
        value_delta[to_key] += weight
        value_delta[from_key] -= weight
        group_delta[to_key][group] += weight
        group_delta[from_key][group] -= weight

    features: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in outcome_rows:
        key = (row["team_id"].strip(), row["nfl_season"].strip(), row["nfl_week"].strip())
        inbound = inbound_counts.get(key, 0)
        outbound = outbound_counts.get(key, 0)
        churn = (inbound + outbound) / roster_size if roster_size > 0 else 0.0
        week_int = parse_int(key[2], "nfl_week")

        opponents = opponents_by_key.get(key, [])
        if opponents:
            avg_opp_strength = sum(
                prior_win_pct(opponent_history, opp, key[1], week_int)
                for opp in opponents
            ) / len(opponents)
        else:
            avg_opp_strength = 0.5

        # Normalize around 0.5 baseline into [-1, 1] style scale.
        schedule_strength = (avg_opp_strength - 0.5) / 0.5

        features[key] = {
            "team_id": key[0],
            "nfl_season": key[1],
            "nfl_week": key[2],
            "roster_churn_rate": f"{churn:.6f}",
            "inbound_move_count": str(inbound),
            "outbound_move_count": str(outbound),
            "offense_skill_value_delta": f"{group_delta.get(key, {}).get('offense_skill', 0.0):.4f}",
            "offense_line_value_delta": f"{group_delta.get(key, {}).get('offense_line', 0.0):.4f}",
            "defense_front_value_delta": f"{group_delta.get(key, {}).get('defense_front', 0.0):.4f}",
            "defense_second_level_value_delta": f"{group_delta.get(key, {}).get('defense_second_level', 0.0):.4f}",
            "defense_secondary_value_delta": f"{group_delta.get(key, {}).get('defense_secondary', 0.0):.4f}",
            "special_teams_value_delta": f"{group_delta.get(key, {}).get('special_teams', 0.0):.4f}",
            "other_value_delta": f"{group_delta.get(key, {}).get('other', 0.0):.4f}",
            "position_value_delta": f"{value_delta.get(key, 0.0):.4f}",
            "schedule_strength_index": f"{schedule_strength:.4f}",
            "feature_version": feature_version,
            "generated_at": generated_at,
        }

    return features


def main() -> None:
    args = parse_args()

    for path in (args.movement, args.players, args.team_games, args.calendar, args.outcomes):
        if not path.exists():
            raise FileNotFoundError(f"missing input file: {path}")

    movement_rows = read_csv(args.movement)
    player_rows = read_csv(args.players)
    team_game_rows = read_csv(args.team_games)
    calendar_lookup = read_calendar_lookup(args.calendar)
    outcome_rows = read_csv(args.outcomes)
    position_weights = load_position_weights(args.position_weights)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    incoming = build_features(
        movement_rows,
        player_rows,
        team_game_rows,
        calendar_lookup,
        outcome_rows,
        position_weights=position_weights,
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
