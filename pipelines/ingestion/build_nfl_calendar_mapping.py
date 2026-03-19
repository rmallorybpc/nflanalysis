#!/usr/bin/env python3
"""Build a canonical NFL date -> season/week mapping table.

The output supports issue #3 dependencies by providing a deterministic calendar
reference that ingestion and feature jobs can join on.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class SeasonBoundaries:
    season: int
    offseason_start: date
    preseason_start: date
    regular_start: date
    regular_end: date
    postseason_end: date


def first_weekday_in_month(year: int, month: int, weekday: int) -> date:
    """Return first weekday occurrence in month.

    weekday uses datetime/date convention: Monday=0, Sunday=6.
    """

    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def first_thursday_after_labor_day(year: int) -> date:
    """Approximate NFL kickoff anchor for regular season week 1.

    Labor Day is the first Monday in September. The first Thursday after that
    date is a stable approximation for week 1 kickoff anchor.
    """

    labor_day = first_weekday_in_month(year, 9, 0)
    d = labor_day + timedelta(days=1)
    while d.weekday() != 3:
        d += timedelta(days=1)
    return d


def build_season_boundaries(start_season: int, end_season: int) -> dict[int, SeasonBoundaries]:
    if end_season < start_season:
        raise ValueError("end_season must be >= start_season")

    regular_starts = {
        season: first_thursday_after_labor_day(season)
        for season in range(start_season - 1, end_season + 1)
    }
    regular_ends = {
        season: regular_starts[season] + timedelta(days=(18 * 7) - 1)
        for season in range(start_season - 1, end_season + 1)
    }
    postseason_ends = {
        season: regular_ends[season] + timedelta(days=(5 * 7) - 1)
        for season in range(start_season - 1, end_season + 1)
    }
    preseason_starts = {
        season: regular_starts[season] - timedelta(days=4 * 7)
        for season in range(start_season - 1, end_season + 1)
    }

    boundaries: dict[int, SeasonBoundaries] = {}
    for season in range(start_season, end_season + 1):
        offseason_start = postseason_ends[season - 1] + timedelta(days=1)
        boundaries[season] = SeasonBoundaries(
            season=season,
            offseason_start=offseason_start,
            preseason_start=preseason_starts[season],
            regular_start=regular_starts[season],
            regular_end=regular_ends[season],
            postseason_end=postseason_ends[season],
        )

    return boundaries


def iter_dates(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def week_label_for(boundary: SeasonBoundaries, day: date) -> tuple[str, str, str]:
    """Return (season_phase, phase_week, nfl_week)."""

    if day < boundary.preseason_start:
        return ("offseason", "", "")

    if day < boundary.regular_start:
        preseason_week = ((day - boundary.preseason_start).days // 7) + 1
        return ("preseason", str(preseason_week), str(preseason_week))

    if day <= boundary.regular_end:
        regular_week = ((day - boundary.regular_start).days // 7) + 1
        return ("regular", str(regular_week), str(regular_week))

    postseason_week = ((day - boundary.regular_end - timedelta(days=1)).days // 7) + 1
    labels = {
        1: "wild_card",
        2: "divisional",
        3: "conference_championship",
        4: "pro_bowl_gap",
        5: "super_bowl",
    }
    label = labels.get(postseason_week, "postseason")
    return ("postseason", label, str(18 + postseason_week))


def build_rows(start_season: int, end_season: int) -> list[dict[str, str]]:
    boundaries = build_season_boundaries(start_season, end_season)
    rows: list[dict[str, str]] = []

    for season in range(start_season, end_season + 1):
        boundary = boundaries[season]
        for day in iter_dates(boundary.offseason_start, boundary.postseason_end):
            season_phase, phase_week, nfl_week = week_label_for(boundary, day)
            rows.append(
                {
                    "calendar_date": day.isoformat(),
                    "nfl_season": str(season),
                    "season_phase": season_phase,
                    "phase_week": phase_week,
                    "nfl_week": nfl_week,
                }
            )

    return rows


def write_rows(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["calendar_date", "nfl_season", "season_phase", "phase_week", "nfl_week"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NFL season/week date mapping table")
    parser.add_argument("--start-season", type=int, default=2018)
    parser.add_argument("--end-season", type=int, default=2030)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/external/nfl_calendar_mapping.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_rows(args.start_season, args.end_season)
    write_rows(rows, args.output)
    print(
        f"Wrote {len(rows)} rows to {args.output} "
        f"for seasons {args.start_season}-{args.end_season}"
    )


if __name__ == "__main__":
    main()
