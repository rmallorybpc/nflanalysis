#!/usr/bin/env python3
"""Precompute static dashboard payloads from CounterfactualService.

This script mirrors the API service bundle loading behavior by using
ServiceConfig.from_env(), then materializes dashboard payloads as static JSON
under dashboard/src/data.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.counterfactual_service import CounterfactualService, ServiceConfig  # noqa: E402


DEFAULT_OUT_DIR = ROOT / "dashboard" / "src" / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build static dashboard payload JSON files")
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Output directory for static JSON files",
    )
    parser.add_argument(
        "--seasons",
        default="",
        help="Comma-separated seasons (default: all seasons available in configured service data)",
    )
    return parser.parse_args()


def now_iso_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_seasons_arg(value: str) -> list[int]:
    raw = value.strip()
    if not raw:
        return []
    seasons: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        seasons.append(int(token))
    unique = sorted(set(seasons))
    return unique


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))


def build_findings_payload(
    overview_by_season: dict[int, dict[str, Any]],
    built_at: str,
) -> dict[str, Any]:
    seasons = sorted(overview_by_season.keys())
    geography: dict[str, list[dict[str, Any]]] = {}
    cards: dict[str, dict[str, Any]] = {}
    for season in seasons:
        payload = overview_by_season[season]
        geography[str(season)] = payload.get("charts", {}).get("geography_impact_profile", [])
        cards[str(season)] = payload.get("cards", {})

    season_coverage: list[dict[str, Any]] = []
    if seasons:
        latest = overview_by_season[seasons[-1]]
        season_coverage = latest.get("charts", {}).get("season_coverage", [])

    return {
        "built_at": built_at,
        "seasons": seasons,
        "season_coverage": season_coverage,
        "cards_by_season": cards,
        "geography_profile_by_season": geography,
    }


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)

    service = CounterfactualService(config=ServiceConfig.from_env())

    configured_seasons = parse_seasons_arg(args.seasons)
    available_seasons = sorted({int(row["nfl_season"]) for row in service.model_rows})
    seasons = configured_seasons if configured_seasons else available_seasons

    team_ids = sorted(
        {
            row["team_id"].strip()
            for row in service.model_rows
            if row.get("outcome_name", "").strip() == "win_pct"
        }
    )

    overview_dir = out_dir / "overview"
    season_dir = out_dir / "season"
    overview_dir.mkdir(parents=True, exist_ok=True)
    season_dir.mkdir(parents=True, exist_ok=True)

    overview_by_season: dict[int, dict[str, Any]] = {}
    model_version = ""

    for season in seasons:
        overview_payload = service.build_overview_payload(season=season)
        overview_by_season[season] = overview_payload
        write_json(overview_dir / f"{season}.json", overview_payload)

        season_payload: dict[str, Any] = {}
        for team_id in team_ids:
            season_payload[team_id] = service.build_team_detail_payload(team_id=team_id, season=season)
        write_json(season_dir / f"{season}.json", season_payload)

        if not model_version:
            top_positive = overview_payload.get("cards", {}).get("top_positive_team", {})
            model_version = str(top_positive.get("model_version", "")).strip()

    built_at = now_iso_utc()
    findings_payload = build_findings_payload(overview_by_season=overview_by_season, built_at=built_at)
    write_json(out_dir / "findings.json", findings_payload)

    manifest = {
        "built_at": built_at,
        "model_version": model_version,
        "seasons": seasons,
        "team_ids": team_ids,
        "bundle": str(getattr(service.config, "model_outputs", "")),
    }
    write_json(out_dir / "manifest.json", manifest)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "seasons": seasons,
                "team_count": len(team_ids),
                "model_version": model_version,
                "built_at": built_at,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
