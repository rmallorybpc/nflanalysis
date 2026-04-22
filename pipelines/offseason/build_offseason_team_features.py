#!/usr/bin/env python3
"""Build 2026 offseason team features with spending and win-total integration."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_TEAM_SPENDING_PATH = Path("data/raw/offseason/team_spending_otc.csv")
DEFAULT_WIN_TOTALS_PATH = Path("data/raw/offseason/win_totals.csv")

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

GROUP_FIELDS = {
    "offense_skill": "offense_skill_value_delta",
    "offense_line": "offense_line_value_delta",
    "defense_front": "defense_front_value_delta",
    "defense_second_level": "defense_second_level_value_delta",
    "defense_secondary": "defense_secondary_value_delta",
    "special_teams": "special_teams_value_delta",
    "other": "other_value_delta",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offseason feature table")
    parser.add_argument("--movement", type=Path, default=Path("data/processed/offseason/movement_events.csv"))
    parser.add_argument("--players", type=Path, default=Path("data/processed/offseason/player_dimension.csv"))
    parser.add_argument("--outcomes", type=Path, default=Path("data/processed/offseason/team_week_outcomes.csv"))
    parser.add_argument("--team-spending", type=Path, default=DEFAULT_TEAM_SPENDING_PATH)
    parser.add_argument("--win-totals", type=Path, default=DEFAULT_WIN_TOTALS_PATH)
    parser.add_argument(
        "--snapshot-year",
        type=int,
        default=None,
        help="If set, prefer year-suffixed raw inputs (e.g., team_spending_otc_2025.csv) when paths are defaults",
    )
    parser.add_argument("--output", type=Path, default=Path("data/processed/offseason/team_week_features.csv"))
    parser.add_argument("--feature-version", type=str, default="0.4.0-offseason")
    parser.add_argument("--roster-size", type=float, default=53.0)
    return parser.parse_args()


def resolve_year_specific_path(path: Path, default_path: Path, year: int | None) -> Path:
    if year is None:
        return path
    if path != default_path:
        return path
    candidate = default_path.with_name(f"{default_path.stem}_{year}{default_path.suffix}")
    if candidate.exists():
        return candidate
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing input file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def z_scores(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    mu = sum(values.values()) / len(values)
    var = sum((v - mu) ** 2 for v in values.values()) / len(values)
    std = var ** 0.5
    if std <= 1e-12:
        return {k: 0.0 for k in values}
    return {k: (v - mu) / std for k, v in values.items()}


def build_features(
    movement_rows: list[dict[str, str]],
    player_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
    spending_rows: list[dict[str, str]],
    win_total_rows: list[dict[str, str]],
    roster_size: float,
    feature_version: str,
    generated_at: str,
) -> list[dict[str, str]]:
    player_pos = {r["player_id"].strip(): (r.get("position") or "").strip().upper() for r in player_rows}
    player_group = {r["player_id"].strip(): (r.get("position_group") or "other").strip().lower() for r in player_rows}

    spending = {
        (r.get("team") or "").strip().upper(): to_float((r.get("total_fa_spending") or "0").strip(), "total_fa_spending")
        for r in spending_rows
        if (r.get("team") or "").strip()
    }
    win_totals = {
        (r.get("team") or "").strip().upper(): to_float((r.get("win_total") or "0").strip(), "win_total")
        for r in win_total_rows
        if (r.get("team") or "").strip()
    }

    spending_z = z_scores(spending)
    win_total_z = z_scores(win_totals)

    inbound: dict[tuple[str, str, str], int] = defaultdict(int)
    outbound: dict[tuple[str, str, str], int] = defaultdict(int)
    group_delta: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    total_delta: dict[tuple[str, str, str], float] = defaultdict(float)

    for row in movement_rows:
        season = (row.get("nfl_season") or "").strip()
        week = (row.get("nfl_week") or "").strip()
        if not season or not week:
            continue

        pid = (row.get("player_id") or "").strip()
        pos = player_pos.get(pid, "")
        group = player_group.get(pid, "other")
        if group not in GROUP_FIELDS:
            group = "other"
        weight = POSITION_WEIGHTS.get(pos, 1.0)

        to_team = (row.get("to_team_id") or "").strip().upper()
        from_team = (row.get("from_team_id") or "").strip().upper()

        if to_team:
            key = (to_team, season, week)
            inbound[key] += 1
            total_delta[key] += weight
            group_delta[key][group] += weight

        if from_team:
            key = (from_team, season, week)
            outbound[key] += 1
            total_delta[key] -= weight
            group_delta[key][group] -= weight

    out: list[dict[str, str]] = []
    schedule_strength_values: list[float] = []
    for row in outcome_rows:
        team = (row.get("team_id") or "").strip().upper()
        season = (row.get("nfl_season") or "").strip()
        week = (row.get("nfl_week") or "").strip()
        key = (team, season, week)

        in_count = inbound.get(key, 0)
        out_count = outbound.get(key, 0)
        churn = (in_count + out_count) / roster_size if roster_size > 0 else 0.0

        spend_factor = spending_z.get(team, 0.0)
        win_factor = win_total_z.get(team, 0.0)

        group_vals = {field: 0.0 for field in GROUP_FIELDS.values()}
        for group, field in GROUP_FIELDS.items():
            group_vals[field] = group_delta.get(key, {}).get(group, 0.0)

        # Integrate spending directly into feature vector via other_value_delta.
        group_vals["other_value_delta"] += 0.5 * spend_factor
        # Preserve contract: position_value_delta equals sum of group deltas.
        position_total = sum(group_vals.values())

        out.append(
            {
                "team_id": team,
                "nfl_season": season,
                "nfl_week": week,
                "roster_churn_rate": f"{churn:.6f}",
                "inbound_move_count": str(in_count),
                "outbound_move_count": str(out_count),
                "offense_skill_value_delta": f"{group_vals['offense_skill_value_delta']:.4f}",
                "offense_line_value_delta": f"{group_vals['offense_line_value_delta']:.4f}",
                "defense_front_value_delta": f"{group_vals['defense_front_value_delta']:.4f}",
                "defense_second_level_value_delta": f"{group_vals['defense_second_level_value_delta']:.4f}",
                "defense_secondary_value_delta": f"{group_vals['defense_secondary_value_delta']:.4f}",
                "special_teams_value_delta": f"{group_vals['special_teams_value_delta']:.4f}",
                "other_value_delta": f"{group_vals['other_value_delta']:.4f}",
                "position_value_delta": f"{position_total:.4f}",
                "schedule_strength_index": "0.0000",
                "feature_version": feature_version,
                "generated_at": generated_at,
            }
        )
        schedule_strength_values.append(win_factor)

    if schedule_strength_values:
        max_abs = max(abs(v) for v in schedule_strength_values)
        if max_abs > 0:
            schedule_strength_values = [v / max_abs for v in schedule_strength_values]

    for row, schedule_strength_value in zip(out, schedule_strength_values):
        row["schedule_strength_index"] = f"{schedule_strength_value:.4f}"

    out.sort(key=lambda r: (r["team_id"], int(r["nfl_season"]), int(r["nfl_week"])))
    return out


def main() -> None:
    args = parse_args()
    args.team_spending = resolve_year_specific_path(args.team_spending, DEFAULT_TEAM_SPENDING_PATH, args.snapshot_year)
    args.win_totals = resolve_year_specific_path(args.win_totals, DEFAULT_WIN_TOTALS_PATH, args.snapshot_year)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    movement_rows = read_csv(args.movement)
    player_rows = read_csv(args.players)
    outcome_rows = read_csv(args.outcomes)
    spending_rows = read_csv(args.team_spending)
    win_total_rows = read_csv(args.win_totals)

    features = build_features(
        movement_rows,
        player_rows,
        outcome_rows,
        spending_rows,
        win_total_rows,
        roster_size=args.roster_size,
        feature_version=args.feature_version,
        generated_at=generated_at,
    )

    write_csv(args.output, CANONICAL_FIELDS, features)
    print(f"Built {len(features)} offseason feature rows at {args.output}")


if __name__ == "__main__":
    main()
