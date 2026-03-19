#!/usr/bin/env python3
"""Ingest and normalize NFL movement events into canonical movement_events table.

This script supports idempotent upsert behavior by `move_id` so repeated runs
with overlapping source rows update existing records and append new records.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


REQUIRED_SOURCE_FIELDS = {
    "move_id",
    "event_date",
    "move_type",
    "player_id",
    "from_team_id",
    "to_team_id",
}

CANONICAL_FIELDS = [
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

ALLOWED_MOVE_TYPES = {"trade", "free_agency"}


@dataclass(frozen=True)
class CalendarRow:
    nfl_season: str
    season_phase: str
    phase_week: str
    nfl_week: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest movement events into canonical table")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/movement_events_source.csv"),
        help="Raw source CSV with movement events",
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
        default=Path("data/processed/movement_events.csv"),
        help="Canonical output CSV",
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


def read_calendar(path: Path) -> dict[str, CalendarRow]:
    rows = read_csv(path)
    mapping: dict[str, CalendarRow] = {}

    for row in rows:
        mapping[row["calendar_date"]] = CalendarRow(
            nfl_season=row["nfl_season"],
            season_phase=row["season_phase"],
            phase_week=row["phase_week"],
            nfl_week=row["nfl_week"],
        )

    return mapping


def validate_source_headers(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("source file has no rows")

    missing = REQUIRED_SOURCE_FIELDS - set(rows[0].keys())
    if missing:
        raise ValueError(f"source file missing required columns: {sorted(missing)}")


def normalize_move_type(value: str) -> str:
    cleaned = value.strip().lower()
    aliases = {
        "free agency": "free_agency",
        "free-agent": "free_agency",
        "free_agent": "free_agency",
        "fa": "free_agency",
    }
    cleaned = aliases.get(cleaned, cleaned)
    if cleaned not in ALLOWED_MOVE_TYPES:
        raise ValueError(f"unsupported move_type: {value}")
    return cleaned


def ensure_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value}") from exc


def canonicalize_row(raw: dict[str, str], calendar: dict[str, CalendarRow], ingested_at: str) -> dict[str, str]:
    event_date = ensure_date(raw["event_date"].strip(), "event_date")
    effective_date = raw.get("effective_date", "").strip() or event_date
    effective_date = ensure_date(effective_date, "effective_date")

    if effective_date not in calendar:
        raise ValueError(
            f"effective_date {effective_date} not found in calendar mapping"
        )

    cal = calendar[effective_date]

    row = {
        "move_id": raw["move_id"].strip(),
        "event_date": event_date,
        "effective_date": effective_date,
        "move_type": normalize_move_type(raw["move_type"]),
        "player_id": raw["player_id"].strip(),
        "from_team_id": raw["from_team_id"].strip(),
        "to_team_id": raw["to_team_id"].strip(),
        "transaction_detail": raw.get("transaction_detail", "").strip(),
        "source": raw.get("source", "manual_seed").strip() or "manual_seed",
        "nfl_season": cal.nfl_season,
        "season_phase": cal.season_phase,
        "phase_week": cal.phase_week,
        "nfl_week": cal.nfl_week,
        "ingested_at": ingested_at,
    }

    if not row["move_id"]:
        raise ValueError("move_id cannot be empty")

    return row


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    rows = read_csv(path)
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        move_id = row.get("move_id", "").strip()
        if move_id:
            by_id[move_id] = row
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
    if not args.calendar.exists():
        raise FileNotFoundError(f"missing calendar file: {args.calendar}")

    raw_rows = read_csv(args.source)
    validate_source_headers(raw_rows)
    calendar = read_calendar(args.calendar)

    ingested_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    incoming: dict[str, dict[str, str]] = {}
    for raw in raw_rows:
        row = canonicalize_row(raw, calendar, ingested_at)
        incoming[row["move_id"]] = row

    if args.replace:
        merged = incoming
    else:
        merged = read_existing(args.output)
        merged.update(incoming)

    sorted_rows = [merged[k] for k in sorted(merged.keys())]
    write_output(sorted_rows, args.output)

    print(
        f"Ingested {len(incoming)} source rows; "
        f"output has {len(sorted_rows)} rows at {args.output}"
    )


if __name__ == "__main__":
    main()
