#!/usr/bin/env python3
"""Build 2026 offseason canonical tables from new raw inputs.

This script ingests the new one-time offseason inputs and writes:
- data/processed/movement_events.csv
- data/processed/player_dimension.csv
- data/processed/team_week_outcomes.csv
- data/processed/offseason_manual_review.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_TRANSACTIONS_PATH = Path("data/raw/offseason/transactions_raw.csv")
DEFAULT_PLAYERS_PATH = Path("data/raw/offseason/players_metadata.csv")
DEFAULT_WIN_TOTALS_PATH = Path("data/raw/offseason/win_totals.csv")

MOVE_TYPE_MAP = {
    "signed": "free_agency",
    "re-signed": "free_agency",
    "resigned": "free_agency",
    "released": "free_agency",
    "waived": "free_agency",
    "claimed": "free_agency",
    "traded": "trade",
}

IGNORE_TYPES = {
    "practice squad",
    "reserve/future",
}

POSITION_GROUP_MAP = {
    "QB": "offense_skill",
    "RB": "offense_skill",
    "FB": "offense_skill",
    "WR": "offense_skill",
    "TE": "offense_skill",
    "OL": "offense_line",
    "LT": "offense_line",
    "LG": "offense_line",
    "C": "offense_line",
    "RG": "offense_line",
    "RT": "offense_line",
    "DL": "defense_front",
    "DE": "defense_front",
    "DT": "defense_front",
    "NT": "defense_front",
    "EDGE": "defense_front",
    "LB": "defense_second_level",
    "ILB": "defense_second_level",
    "OLB": "defense_second_level",
    "CB": "defense_secondary",
    "S": "defense_secondary",
    "FS": "defense_secondary",
    "SS": "defense_secondary",
    "K": "special_teams",
    "P": "special_teams",
    "LS": "special_teams",
}

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

REVIEW_FIELDS = [
    "issue_type",
    "transaction_date",
    "team",
    "player",
    "transaction_type",
    "notes",
]


TEAM_CODE_RE = re.compile(r"\b([A-Z]{2,3})\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest one-time offseason snapshot")
    parser.add_argument("--transactions", type=Path, default=DEFAULT_TRANSACTIONS_PATH)
    parser.add_argument("--players", type=Path, default=DEFAULT_PLAYERS_PATH)
    parser.add_argument("--win-totals", type=Path, default=DEFAULT_WIN_TOTALS_PATH)
    parser.add_argument(
        "--snapshot-year",
        type=int,
        default=None,
        help="If set, prefer year-suffixed raw inputs (e.g., transactions_raw_2025.csv) when paths are defaults",
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=1)
    parser.add_argument("--movement-output", type=Path, default=Path("data/processed/offseason/movement_events.csv"))
    parser.add_argument("--players-output", type=Path, default=Path("data/processed/offseason/player_dimension.csv"))
    parser.add_argument("--outcomes-output", type=Path, default=Path("data/processed/offseason/team_week_outcomes.csv"))
    parser.add_argument("--review-output", type=Path, default=Path("data/processed/offseason/manual_review.csv"))
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


def clean_team(value: str) -> str:
    return (value or "").strip().upper()


def clean_type(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def build_player_dimension(rows: list[dict[str, str]], as_of_year: int, now_iso: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    out: list[dict[str, str]] = []
    by_name: dict[str, str] = {}

    for row in rows:
        name = (row.get("player") or "").strip()
        player_id = (row.get("pfr_slug") or "").strip()
        position = (row.get("position") or "").strip().upper() or "UNK"
        if not name or not player_id:
            continue

        draft_year_raw = (row.get("draft_year") or "").strip()
        rookie_year = int(draft_year_raw) if draft_year_raw.isdigit() else max(as_of_year - 1, 2000)
        exp = max(as_of_year - rookie_year, 0)
        group = POSITION_GROUP_MAP.get(position, "other")

        out.append(
            {
                "player_id": player_id,
                "full_name": name,
                "position_group": group,
                "position": position,
                "birth_date": "1900-01-01",
                "rookie_year": str(rookie_year),
                "experience_years": str(exp),
                "active_status": "active",
                "source": (row.get("source_url") or "manual").strip() or "manual",
                "normalized_at": now_iso,
            }
        )
        by_name[name.lower()] = player_id

    out.sort(key=lambda r: r["player_id"])
    return out, by_name


def parse_trade_teams(row: dict[str, str]) -> tuple[str, str, bool]:
    explicit_from = clean_team(row.get("from_team_id", ""))
    explicit_to = clean_team(row.get("to_team_id", ""))
    if explicit_from or explicit_to:
        return explicit_from, explicit_to, False

    notes = (row.get("notes") or "").upper()
    found = TEAM_CODE_RE.findall(notes)
    if len(found) >= 2:
        return clean_team(found[0]), clean_team(found[1]), False
    return "", "", True


def map_transaction_teams(tx_type: str, team: str, row: dict[str, str]) -> tuple[str, str, bool]:
    if tx_type == "signed" or tx_type == "claimed":
        return "", team, False
    if tx_type == "re-signed" or tx_type == "resigned":
        return team, team, False
    if tx_type == "released" or tx_type == "waived":
        return team, "", False
    if tx_type == "traded":
        return parse_trade_teams(row)
    return "", "", False


def build_movement_events(
    rows: list[dict[str, str]],
    player_by_name: dict[str, str],
    season: int,
    week: int,
    now_iso: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    out: list[dict[str, str]] = []
    review: list[dict[str, str]] = []

    for idx, row in enumerate(rows, start=1):
        tx_type = clean_type(row.get("transaction_type", ""))
        if tx_type in IGNORE_TYPES or tx_type not in MOVE_TYPE_MAP:
            continue

        team = clean_team(row.get("team", ""))
        player_name = (row.get("player") or "").strip()
        player_id = player_by_name.get(player_name.lower(), "")

        if not player_id:
            review.append(
                {
                    "issue_type": "missing_player_id",
                    "transaction_date": (row.get("transaction_date") or "").strip(),
                    "team": team,
                    "player": player_name,
                    "transaction_type": tx_type,
                    "notes": "player not found in players_metadata.csv by exact name",
                }
            )
            continue

        from_team, to_team, needs_review = map_transaction_teams(tx_type, team, row)

        detail = (row.get("notes") or "").strip()
        if needs_review:
            review.append(
                {
                    "issue_type": "trade_missing_explicit_teams",
                    "transaction_date": (row.get("transaction_date") or "").strip(),
                    "team": team,
                    "player": player_name,
                    "transaction_type": tx_type,
                    "notes": "trade with unresolved from/to team ids",
                }
            )
            detail = (detail + " | manual_review:missing_trade_teams").strip(" |")

        event_date = (row.get("transaction_date") or "").strip()
        move_id = f"ofs_{season}_{week:02d}_{idx:05d}"

        out.append(
            {
                "move_id": move_id,
                "event_date": event_date,
                "effective_date": event_date,
                "move_type": MOVE_TYPE_MAP[tx_type],
                "player_id": player_id,
                "from_team_id": from_team,
                "to_team_id": to_team,
                "transaction_detail": detail,
                "source": (row.get("source_url") or "manual").strip() or "manual",
                "nfl_season": str(season),
                "season_phase": "regular",
                "phase_week": str(week),
                "nfl_week": str(week),
                "ingested_at": now_iso,
            }
        )

    out.sort(key=lambda r: r["move_id"])
    return out, review


def build_outcomes_from_win_totals(rows: list[dict[str, str]], season: int, week: int, now_iso: str) -> list[dict[str, str]]:
    values: list[tuple[str, float]] = []
    for row in rows:
        team = clean_team(row.get("team", ""))
        if not team:
            continue
        values.append((team, to_float((row.get("win_total") or "").strip(), "win_total")))

    if not values:
        raise ValueError("win_totals.csv must contain at least one team")

    league_avg = sum(v for _, v in values) / len(values)

    out: list[dict[str, str]] = []
    for team, win_total in sorted(values):
        win_pct = max(min(win_total / 17.0, 1.0), 0.0)
        point_diff = (win_total - league_avg) * 1.5
        off_epa = (win_total - league_avg) * 0.01
        wins = int(round(win_total))

        out.append(
            {
                "team_id": team,
                "nfl_season": str(season),
                "nfl_week": str(week),
                "games_played": "1",
                "wins": str(max(min(wins, 17), 0)),
                "losses": "0",
                "ties": "0",
                "win_pct": f"{win_pct:.4f}",
                "point_diff_per_game": f"{point_diff:.4f}",
                "offensive_epa_per_play": f"{off_epa:.4f}",
                "aggregated_at": now_iso,
            }
        )

    return out


def main() -> None:
    args = parse_args()
    args.transactions = resolve_year_specific_path(args.transactions, DEFAULT_TRANSACTIONS_PATH, args.snapshot_year)
    args.players = resolve_year_specific_path(args.players, DEFAULT_PLAYERS_PATH, args.snapshot_year)
    args.win_totals = resolve_year_specific_path(args.win_totals, DEFAULT_WIN_TOTALS_PATH, args.snapshot_year)

    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    tx_rows = read_csv(args.transactions)
    player_rows = read_csv(args.players)
    win_total_rows = read_csv(args.win_totals)

    players_out, player_by_name = build_player_dimension(player_rows, args.season, now_iso)
    movement_out, review_out = build_movement_events(tx_rows, player_by_name, args.season, args.week, now_iso)
    outcomes_out = build_outcomes_from_win_totals(win_total_rows, args.season, args.week, now_iso)

    write_csv(args.players_output, PLAYER_FIELDS, players_out)
    write_csv(args.movement_output, MOVEMENT_FIELDS, movement_out)
    write_csv(args.outcomes_output, OUTCOME_FIELDS, outcomes_out)
    write_csv(args.review_output, REVIEW_FIELDS, review_out)

    print(
        "Built offseason snapshot tables: "
        f"players={len(players_out)}, movements={len(movement_out)}, outcomes={len(outcomes_out)}, "
        f"manual_review={len(review_out)}"
    )


if __name__ == "__main__":
    main()
