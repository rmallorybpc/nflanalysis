#!/usr/bin/env python3
"""Resolve 2026 NFL win totals from collected evidence rows."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_TEAMS = [
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

PROVIDER_PRIORITY = [
    "DraftKings",
    "FanDuel",
    "BetMGM",
    "Caesars",
    "RiversCasino",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve win totals from evidence")
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("data/raw/offseason/win_totals_2026_evidence_template.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/offseason/win_totals_2026.csv"),
    )
    parser.add_argument(
        "--unresolved",
        type=Path,
        default=Path("data/raw/offseason/win_totals_2026_unresolved.csv"),
    )
    parser.add_argument(
        "--captured-at",
        default="",
        help="Optional fixed captured_at timestamp; defaults to current UTC time.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ts_value(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v).isoformat()
    except ValueError:
        return ""


def ts_epoch(value: str) -> float:
    v = (value or "").strip()
    if not v:
        return 0.0
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v).timestamp()
    except ValueError:
        return 0.0


def pick_best(rows: list[dict[str, str]]) -> dict[str, str] | None:
    if not rows:
        return None

    def sort_key(row: dict[str, str]) -> tuple[int, float, str, str]:
        provider = (row.get("provider") or "").strip()
        try:
            provider_rank = PROVIDER_PRIORITY.index(provider)
        except ValueError:
            provider_rank = len(PROVIDER_PRIORITY)

        observed_epoch = ts_epoch(row.get("observed_at") or "")
        win_total = (row.get("win_total") or "").strip()
        source_url = (row.get("source_url") or "").strip()
        return (provider_rank, -observed_epoch, win_total, source_url)

    return sorted(rows, key=sort_key)[0]


def normalize_evidence(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for row in rows:
        team = (row.get("team") or "").strip()
        win_total = (row.get("win_total") or "").strip()
        if team not in CANONICAL_TEAMS:
            continue
        if not win_total:
            continue
        try:
            float(win_total)
        except ValueError:
            continue
        clean.append(
            {
                "team": team,
                "win_total": win_total,
                "provider": (row.get("provider") or "").strip(),
                "source_url": (row.get("source_url") or "").strip(),
                "observed_at": (row.get("observed_at") or "").strip(),
            }
        )
    return clean


def main() -> None:
    args = parse_args()
    if not args.evidence.exists():
        raise FileNotFoundError(f"Missing evidence file: {args.evidence}")

    captured_at = args.captured_at.strip() or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = normalize_evidence(read_csv(args.evidence))

    by_team: dict[str, list[dict[str, str]]] = {team: [] for team in CANONICAL_TEAMS}
    for row in evidence:
        by_team[row["team"]].append(row)

    resolved_rows: list[dict[str, str]] = []
    unresolved_rows: list[dict[str, str]] = []

    for team in CANONICAL_TEAMS:
        team_rows = by_team[team]
        best = pick_best(team_rows)
        if best is None:
            attempted = sorted({r.get("source_url", "") for r in evidence if r.get("source_url", "")})
            unresolved_rows.append(
                {
                    "team": team,
                    "reason": "source_unverifiable",
                    "attempted_sources": "|".join(attempted),
                }
            )
            continue

        resolved_rows.append(
            {
                "team": team,
                "win_total": best["win_total"],
                "provider": best["provider"],
                "captured_at": captured_at,
            }
        )

    write_csv(args.output, ["team", "win_total", "provider", "captured_at"], resolved_rows)
    write_csv(args.unresolved, ["team", "reason", "attempted_sources"], unresolved_rows)

    print(f"evidence_rows={len(evidence)} resolved={len(resolved_rows)} unresolved={len(unresolved_rows)}")


if __name__ == "__main__":
    main()
