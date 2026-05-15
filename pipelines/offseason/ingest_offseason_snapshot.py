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
DEFAULT_CALENDAR_PATH = Path("data/external/nfl_calendar_mapping.csv")

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

TEAM_DIVISION = {
    # AFC East
    "BUF": ("AFC", "AFC East"),
    "MIA": ("AFC", "AFC East"),
    "NE": ("AFC", "AFC East"),
    "NYJ": ("AFC", "AFC East"),
    # AFC North
    "BAL": ("AFC", "AFC North"),
    "CIN": ("AFC", "AFC North"),
    "CLE": ("AFC", "AFC North"),
    "PIT": ("AFC", "AFC North"),
    # AFC South
    "HOU": ("AFC", "AFC South"),
    "IND": ("AFC", "AFC South"),
    "JAX": ("AFC", "AFC South"),
    "TEN": ("AFC", "AFC South"),
    # AFC West
    "DEN": ("AFC", "AFC West"),
    "KC": ("AFC", "AFC West"),
    "LV": ("AFC", "AFC West"),
    "LAC": ("AFC", "AFC West"),
    # NFC East
    "DAL": ("NFC", "NFC East"),
    "NYG": ("NFC", "NFC East"),
    "PHI": ("NFC", "NFC East"),
    "WAS": ("NFC", "NFC East"),
    # NFC North
    "CHI": ("NFC", "NFC North"),
    "DET": ("NFC", "NFC North"),
    "GB": ("NFC", "NFC North"),
    "MIN": ("NFC", "NFC North"),
    # NFC South
    "ATL": ("NFC", "NFC South"),
    "CAR": ("NFC", "NFC South"),
    "NO": ("NFC", "NFC South"),
    "TB": ("NFC", "NFC South"),
    # NFC West
    "ARI": ("NFC", "NFC West"),
    "LAR": ("NFC", "NFC West"),
    "SEA": ("NFC", "NFC West"),
    "SF": ("NFC", "NFC West"),
}

MOVEMENT_FIELDS = [
    "move_id",
    "event_date",
    "effective_date",
    "move_type",
    "player_id",
    "from_team_id",
    "to_team_id",
    "move_scope",
    "contract_aav",
    "contract_total",
    "contract_years",
    "transaction_detail",
    "source",
    "nfl_season",
    "season_phase",
    "phase_week",
    "nfl_week",
    "season_anomaly",
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
NFL_PROFILE_RE = re.compile(r"https?://(?:www\.)?nfl\.com/players/([^/?#]+)/?", re.IGNORECASE)


def _name_fallback_player_id(name: str, position: str) -> str:
    normalized_name = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    normalized_position = re.sub(r"[^a-z0-9]+", "", (position or "").strip().lower()) or "unk"
    if not normalized_name:
        return ""
    # Deterministic fallback for records without PFR/NFL profile identifiers.
    return f"name:{normalized_name}:{normalized_position}"


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
    parser.add_argument(
        "--blocklist",
        default="data/raw/offseason/player_blocklist.csv",
        help="Path to player blocklist CSV",
    )
    parser.add_argument("--append", action="store_true", default=False)
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


def read_csv_if_exists(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_blocklist(blocklist_path: Path) -> set[tuple[str, str, str]]:
    """
    Returns a set of (lowercased_player_name, team_upper, season_str)
    tuples to exclude from movement event generation.
    An empty team value means block the player from ALL teams
    for that season.
    """
    if not blocklist_path.exists():
        return set()
    blocked: set[tuple[str, str, str]] = set()
    with open(blocklist_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("player_name", "").strip().lower()
            team = row.get("team", "").strip().upper()
            season = row.get("season", "").strip()
            if name and season:
                blocked.add((name, team, season))
    return blocked


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    write_header = True
    if append and path.exists() and path.stat().st_size > 0:
        write_header = False

    with path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def clean_team(value: str) -> str:
    return (value or "").strip().upper()


def clean_type(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def resolve_anchor_effective_date(season: int, week: int) -> str:
    rows = read_csv(DEFAULT_CALENDAR_PATH)
    candidates = [
        (row.get("calendar_date") or "").strip()
        for row in rows
        if (row.get("nfl_season") or "").strip() == str(season)
        and (row.get("season_phase") or "").strip() == "regular"
        and (row.get("nfl_week") or "").strip() == str(week)
        and (row.get("calendar_date") or "").strip()
    ]
    if not candidates:
        raise ValueError(
            f"could not find calendar anchor for season={season}, week={week} in {DEFAULT_CALENDAR_PATH}"
        )
    return sorted(candidates)[0]


def to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def compute_move_scope(from_team: str, to_team: str) -> str:
    from_team_id = (from_team or "").strip().upper()
    to_team_id = (to_team or "").strip().upper()
    if not from_team_id or not to_team_id:
        return "unknown"

    from_info = TEAM_DIVISION.get(from_team_id)
    to_info = TEAM_DIVISION.get(to_team_id)
    if not from_info or not to_info:
        return "unknown"

    if from_info[1] == to_info[1]:
        return "same_division"
    if from_info[0] == to_info[0]:
        return "cross_division"
    return "cross_conference"


def derive_player_id(row: dict[str, str]) -> str:
    pfr = (row.get("pfr_slug") or "").strip()
    if pfr:
        return pfr

    source_url = (row.get("source_url") or "").strip()
    m = NFL_PROFILE_RE.search(source_url)
    if m:
        # Prefix keeps NFL-derived IDs distinct from canonical PFR slugs.
        return f"nfl:{m.group(1).lower()}"

    player_name = (row.get("player") or "").strip()
    position = (row.get("position") or "").strip()
    fallback_id = _name_fallback_player_id(player_name, position)
    if fallback_id:
        return fallback_id

    return ""


def build_player_dimension(rows: list[dict[str, str]], as_of_year: int, now_iso: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    out: list[dict[str, str]] = []
    by_name: dict[str, str] = {}

    for row in rows:
        name = (row.get("player") or "").strip()
        player_id = derive_player_id(row)
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


def infer_players_metadata_move_type(row: dict[str, str]) -> str:
    explicit_move_type = clean_type(row.get("move_type", ""))
    if explicit_move_type in {"trade", "free_agency"}:
        return explicit_move_type

    tx_type = clean_type(row.get("transaction_type", ""))
    if tx_type in MOVE_TYPE_MAP:
        return MOVE_TYPE_MAP[tx_type]

    import_method = clean_type(row.get("import_method", ""))
    if "trade" in import_method:
        return "trade"

    return "free_agency"


def build_movement_events(
    rows: list[dict[str, str]],
    player_by_name: dict[str, str],
    season: int,
    week: int,
    now_iso: str,
    blocklist: set[tuple[str, str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    out: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    anchor_effective_date = resolve_anchor_effective_date(season, week)
    season_anomaly = "covid_season" if season == 2020 else ""
    inferred_players_metadata_mode = bool(rows) and "transaction_type" not in rows[0]

    for idx, row in enumerate(rows, start=1):
        if inferred_players_metadata_mode:
            team = clean_team(row.get("team", ""))
            from_team = clean_team(row.get("from_team", ""))
            if not team:
                continue

            # Draft additions (no prior team in offseason metadata) are not movement events.
            draft_year_raw = (row.get("draft_year") or "").strip()
            experience_raw = (row.get("experience") or "").strip()
            is_current_draft_pick = False
            if not from_team and draft_year_raw:
                try:
                    draft_year = int(float(draft_year_raw))
                except ValueError:
                    draft_year = None
                if draft_year == season:
                    if not experience_raw:
                        is_current_draft_pick = True
                    else:
                        try:
                            is_current_draft_pick = int(float(experience_raw)) == 0
                        except ValueError:
                            is_current_draft_pick = False
            if is_current_draft_pick:
                continue

            player_name = (row.get("player") or "").strip()
            player_id = derive_player_id(row) or player_by_name.get(player_name.lower(), "")
            if not player_id:
                review.append(
                    {
                        "issue_type": "missing_player_id",
                        "transaction_date": anchor_effective_date,
                        "team": team,
                        "player": player_name,
                        "transaction_type": "inferred_players_metadata",
                        "notes": "players_metadata row missing pfr_slug and could not map name",
                    }
                )
                continue

            move_id = f"ofs_{season}_{week:02d}_{idx:05d}"
            move_type = infer_players_metadata_move_type(row)
            if from_team and from_team != team and move_type != "trade":
                move_type = "trade"

            # Blocklist check
            player_lower = str(row.get("player", "")).strip().lower()
            to_team_upper = str(team).strip().upper()
            season_str = str(season).strip()

            blocked_this_player = (
                (player_lower, to_team_upper, season_str) in blocklist
                or (player_lower, "", season_str) in blocklist
            )

            if blocked_this_player:
                print(
                    f"[BLOCKLIST] Skipping {row.get('player')} "
                    f"-> {to_team_upper} season={season_str}"
                )
                continue

            from_team_id = (row.get("from_team", "") or "").strip()
            out.append(
                {
                    "move_id": move_id,
                    "event_date": anchor_effective_date,
                    "effective_date": anchor_effective_date,
                    "move_type": move_type,
                    "player_id": player_id,
                    "from_team_id": from_team_id,
                    "to_team_id": team,
                    "move_scope": compute_move_scope(from_team_id, team),
                    "contract_aav": (row.get("contract_aav") or "").strip(),
                    "contract_total": (row.get("contract_total") or "").strip(),
                    "contract_years": (row.get("contract_years") or "").strip(),
                    "transaction_detail": "inferred_from_players_metadata",
                    "source": (row.get("source_url") or "manual").strip() or "manual",
                    "nfl_season": str(season),
                    "season_phase": "regular",
                    "phase_week": str(week),
                    "nfl_week": str(week),
                    "season_anomaly": season_anomaly,
                    "ingested_at": now_iso,
                }
            )
            continue

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

        event_date = (row.get("transaction_date") or "").strip() or anchor_effective_date
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
                "move_scope": compute_move_scope(from_team, to_team),
                "contract_aav": (row.get("contract_aav") or "").strip(),
                "contract_total": (row.get("contract_total") or "").strip(),
                "contract_years": (row.get("contract_years") or "").strip(),
                "transaction_detail": detail,
                "source": (row.get("source_url") or "manual").strip() or "manual",
                "nfl_season": str(season),
                "season_phase": "regular",
                "phase_week": str(week),
                "nfl_week": str(week),
                "season_anomaly": season_anomaly,
                "ingested_at": now_iso,
            }
        )

    out.sort(key=lambda r: r["move_id"])
    return out, review


def build_outcomes_from_win_totals(rows: list[dict[str, str]], season: int, week: int, now_iso: str) -> list[dict[str, str]]:
    if not rows:
        raise ValueError("win_totals.csv must contain at least one team")

    has_actual_columns = all(
        key in rows[0]
        for key in ["wins", "losses", "ties", "win_pct", "point_diff_per_game", "games_played"]
    )

    if has_actual_columns:
        values: list[tuple[str, float]] = []
        normalized_rows: list[dict[str, str]] = []
        for row in rows:
            team = clean_team(row.get("team", ""))
            if not team:
                continue

            wins = int(round(to_float((row.get("wins") or "0").strip(), "wins")))
            losses = int(round(to_float((row.get("losses") or "0").strip(), "losses")))
            ties = int(round(to_float((row.get("ties") or "0").strip(), "ties")))
            games_played = int(round(to_float((row.get("games_played") or "0").strip(), "games_played")))
            point_diff = to_float((row.get("point_diff_per_game") or "0").strip(), "point_diff_per_game")

            win_total = float(wins) + 0.5 * float(ties)
            values.append((team, win_total))
            normalized_rows.append(
                {
                    "team": team,
                    "wins": str(max(wins, 0)),
                    "losses": str(max(losses, 0)),
                    "ties": str(max(ties, 0)),
                    "games_played": str(max(games_played, 0)),
                    "win_pct": f"{to_float((row.get('win_pct') or '0').strip(), 'win_pct'):.4f}",
                    "point_diff_per_game": f"{point_diff:.4f}",
                    "captured_at": (row.get("captured_at") or now_iso).strip() or now_iso,
                }
            )

        league_avg_win_total = sum(v for _, v in values) / len(values) if values else 0.0
        out: list[dict[str, str]] = []
        for row in sorted(normalized_rows, key=lambda r: r["team"]):
            wins = int(row["wins"])
            losses = int(row["losses"])
            ties = int(row["ties"])
            win_total = float(wins) + 0.5 * float(ties)
            off_epa = (win_total - league_avg_win_total) * 0.01

            out.append(
                {
                    "team_id": row["team"],
                    "nfl_season": str(season),
                    "nfl_week": str(week),
                    "games_played": row["games_played"],
                    "wins": row["wins"],
                    "losses": row["losses"],
                    "ties": row["ties"],
                    "win_pct": row["win_pct"],
                    "point_diff_per_game": row["point_diff_per_game"],
                    "offensive_epa_per_play": f"{off_epa:.4f}",
                    "aggregated_at": row["captured_at"],
                }
            )

        return out

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
        games_played = 17
        wins = max(min(int(round(win_total)), games_played), 0)
        losses = games_played - wins

        out.append(
            {
                "team_id": team,
                "nfl_season": str(season),
                "nfl_week": str(week),
                "games_played": str(games_played),
                "wins": str(wins),
                "losses": str(losses),
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
    blocklist = _load_blocklist(Path(args.blocklist))
    if blocklist:
        print(f"[BLOCKLIST] Loaded {len(blocklist)} blocked entries")

    tx_rows = read_csv(args.transactions)
    player_rows = read_csv(args.players)
    win_total_rows = read_csv(args.win_totals)

    players_out, player_by_name = build_player_dimension(player_rows, args.season, now_iso)
    movement_out, review_out = build_movement_events(
        tx_rows,
        player_by_name,
        args.season,
        args.week,
        now_iso,
        blocklist,
    )
    outcomes_out = build_outcomes_from_win_totals(win_total_rows, args.season, args.week, now_iso)

    skipped_existing_players = 0
    skipped_existing_moves = 0
    skipped_existing_outcomes = 0
    if args.append:
        existing_player_ids = {
            (row.get("player_id") or "").strip()
            for row in read_csv_if_exists(args.players_output)
            if (row.get("player_id") or "").strip()
        }
        filtered_players: list[dict[str, str]] = []
        for row in players_out:
            player_id = (row.get("player_id") or "").strip()
            if player_id in existing_player_ids:
                skipped_existing_players += 1
                continue
            existing_player_ids.add(player_id)
            filtered_players.append(row)
        players_out = filtered_players

        existing_move_ids = {
            (row.get("move_id") or "").strip()
            for row in read_csv_if_exists(args.movement_output)
            if (row.get("move_id") or "").strip()
        }
        filtered_moves: list[dict[str, str]] = []
        for row in movement_out:
            move_id = (row.get("move_id") or "").strip()
            if move_id in existing_move_ids:
                skipped_existing_moves += 1
                continue
            existing_move_ids.add(move_id)
            filtered_moves.append(row)
        movement_out = filtered_moves

        existing_outcome_keys = {
            (
                (row.get("team_id") or "").strip(),
                (row.get("nfl_season") or "").strip(),
                (row.get("nfl_week") or "").strip(),
            )
            for row in read_csv_if_exists(args.outcomes_output)
        }
        filtered_outcomes: list[dict[str, str]] = []
        for row in outcomes_out:
            key = (
                (row.get("team_id") or "").strip(),
                (row.get("nfl_season") or "").strip(),
                (row.get("nfl_week") or "").strip(),
            )
            if key in existing_outcome_keys:
                skipped_existing_outcomes += 1
                continue
            existing_outcome_keys.add(key)
            filtered_outcomes.append(row)
        outcomes_out = filtered_outcomes

    write_csv(args.players_output, PLAYER_FIELDS, players_out, append=args.append)
    write_csv(args.movement_output, MOVEMENT_FIELDS, movement_out, append=args.append)
    write_csv(args.outcomes_output, OUTCOME_FIELDS, outcomes_out, append=args.append)
    write_csv(args.review_output, REVIEW_FIELDS, review_out, append=args.append)

    print(
        "Built offseason snapshot tables: "
        f"players={len(players_out)}, movements={len(movement_out)}, outcomes={len(outcomes_out)}, "
        f"manual_review={len(review_out)}"
    )
    if args.append:
        print(
            "Skipped existing rows while appending: "
            f"players={skipped_existing_players}, moves={skipped_existing_moves}, outcomes={skipped_existing_outcomes}"
        )


if __name__ == "__main__":
    main()
