#!/usr/bin/env python3
"""Normalize player metadata into a canonical player dimension table.

The script is idempotent by player_id and can upsert source rows into an
existing output table.
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path


REQUIRED_SOURCE_FIELDS = {
    "player_id",
    "full_name",
    "position",
    "birth_date",
    "rookie_year",
}

CANONICAL_FIELDS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize player metadata")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/player_metadata_source.csv"),
        help="Raw player metadata source CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/player_dimension.csv"),
        help="Canonical player dimension output CSV",
    )
    parser.add_argument(
        "--as-of-year",
        type=int,
        default=datetime.now(UTC).year,
        help="Reference year for experience calculation",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace output instead of upserting into existing output",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_source_headers(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("source file has no rows")

    missing = REQUIRED_SOURCE_FIELDS - set(rows[0].keys())
    if missing:
        raise ValueError(f"source file missing required columns: {sorted(missing)}")


def normalize_position(position: str) -> tuple[str, str]:
    pos = position.strip().upper()
    if not pos:
        raise ValueError("position cannot be empty")

    pos_group = POSITION_GROUP_MAP.get(pos, "other")
    return pos_group, pos


def ensure_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value}") from exc


def to_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer, got {value}") from exc


def canonicalize_row(raw: dict[str, str], as_of_year: int, normalized_at: str) -> dict[str, str]:
    player_id = raw["player_id"].strip()
    if not player_id:
        raise ValueError("player_id cannot be empty")

    full_name = raw["full_name"].strip()
    if not full_name:
        raise ValueError(f"full_name cannot be empty for player_id={player_id}")

    pos_group, pos = normalize_position(raw["position"])
    birth_date = ensure_date(raw["birth_date"].strip(), "birth_date")
    rookie_year = to_int(raw["rookie_year"].strip(), "rookie_year")

    if rookie_year > as_of_year:
        raise ValueError(
            f"rookie_year cannot be in future for player_id={player_id}: {rookie_year}"
        )

    experience = max(as_of_year - rookie_year, 0)
    active_status = raw.get("active_status", "active").strip().lower() or "active"
    source = raw.get("source", "manual_seed").strip() or "manual_seed"

    return {
        "player_id": player_id,
        "full_name": full_name,
        "position_group": pos_group,
        "position": pos,
        "birth_date": birth_date,
        "rookie_year": str(rookie_year),
        "experience_years": str(experience),
        "active_status": active_status,
        "source": source,
        "normalized_at": normalized_at,
    }


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    rows = read_csv(path)
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("player_id", "").strip()
        if key:
            by_id[key] = row
    return by_id


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

    raw_rows = read_csv(args.source)
    validate_source_headers(raw_rows)

    normalized_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    incoming: dict[str, dict[str, str]] = {}
    for raw in raw_rows:
        row = canonicalize_row(raw, args.as_of_year, normalized_at)
        incoming[row["player_id"]] = row

    if args.replace:
        merged = incoming
    else:
        merged = read_existing(args.output)
        merged.update(incoming)

    sorted_rows = [merged[k] for k in sorted(merged.keys())]
    write_output(sorted_rows, args.output)

    print(
        f"Normalized {len(incoming)} source rows; "
        f"output has {len(sorted_rows)} rows at {args.output}"
    )


if __name__ == "__main__":
    main()
