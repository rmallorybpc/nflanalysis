#!/usr/bin/env python3
"""Counterfactual simulation service for movement impact scenarios."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OUTCOME_ORDER = ["win_pct", "point_diff_per_game", "offensive_epa_per_play"]


def _to_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric, got {value}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _interval(low: float, high: float) -> dict[str, float]:
    return {"low": round(low, 6), "high": round(high, 6)}


@dataclass
class ServiceConfig:
    """Input sources for the counterfactual service."""

    model_outputs: Path = Path("data/processed/model_outputs_hierarchical.csv")
    fallback_outputs: Path = Path("data/processed/model_outputs.csv")
    effects: Path = Path("models/artifacts/hierarchical_effects.csv")
    players: Path = Path("data/processed/player_dimension.csv")


class CounterfactualService:
    """Loads model artifacts and computes scenario deltas with uncertainty."""

    def __init__(self, config: ServiceConfig | None = None) -> None:
        self.config = config or ServiceConfig()
        self.model_rows = self._load_model_rows()
        self.effect_map = self._load_effects()
        self.player_group = self._load_player_groups()
        self.mis_stats = self._build_mis_stats()

    def _load_model_rows(self) -> list[dict[str, str]]:
        if self.config.model_outputs.exists():
            rows = _read_csv(self.config.model_outputs)
            if rows:
                return rows
        return _read_csv(self.config.fallback_outputs)

    def _load_effects(self) -> dict[tuple[str, str, str], float]:
        out: dict[tuple[str, str, str], float] = {}
        for row in _read_csv(self.config.effects):
            outcome = row["outcome_name"].strip()
            effect_type = row["effect_type"].strip()
            effect_key = row["effect_key"].strip()
            out[(outcome, effect_type, effect_key)] = _to_float(row["shrunk_effect"], "shrunk_effect")
        return out

    def _load_player_groups(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in _read_csv(self.config.players):
            out[row["player_id"].strip()] = (row.get("position_group", "") or "other").strip().lower()
        return out

    def _build_mis_stats(self) -> dict[str, tuple[float, float]]:
        grouped: dict[str, list[float]] = {}
        for row in self.model_rows:
            outcome = row["outcome_name"].strip()
            grouped.setdefault(outcome, []).append(_to_float(row["mis_value"], "mis_value"))

        stats: dict[str, tuple[float, float]] = {}
        for outcome, values in grouped.items():
            if not values:
                stats[outcome] = (0.0, 1.0)
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = variance ** 0.5
            stats[outcome] = (mean, std if std > 0 else 1.0)
        return stats

    def _team_base_rows(self, team_id: str, season: int, week: int | None) -> list[dict[str, str]]:
        rows = [
            row
            for row in self.model_rows
            if row["team_id"].strip() == team_id and int(row["nfl_season"]) == season
        ]
        if not rows:
            raise ValueError(f"no model outputs for team_id={team_id} season={season}")

        if week is None:
            latest_week = max(int(row["nfl_week"]) for row in rows)
            rows = [row for row in rows if int(row["nfl_week"]) == latest_week]
        else:
            rows = [row for row in rows if int(row["nfl_week"]) == week]
            if not rows:
                raise ValueError(f"no model outputs for team_id={team_id} season={season} week={week}")

        rows.sort(key=lambda row: OUTCOME_ORDER.index(row["outcome_name"]))
        return rows

    def _scenario_adjustment(self, team_id: str, outcome_name: str, moves: list[dict[str, Any]]) -> float:
        adjustment = 0.0
        for move in moves:
            player_id = str(move.get("player_id", "")).strip()
            action = str(move.get("action", "")).strip().lower()
            from_team = str(move.get("from_team_id", "")).strip()
            to_team = str(move.get("to_team_id", "")).strip()

            direction = 0.0
            if action == "add" and to_team == team_id:
                direction = 1.0
            elif action == "remove" and from_team == team_id:
                direction = -1.0
            else:
                continue

            if player_id:
                adjustment += direction * self.effect_map.get((outcome_name, "player", player_id), 0.0)

                position_group = self.player_group.get(player_id, "other")
                key = f"{position_group}|{team_id}"
                adjustment += direction * self.effect_map.get((outcome_name, "position_team", key), 0.0)

        return adjustment

    def _build_estimate(self, row: dict[str, str], adjustment: float) -> dict[str, Any]:
        outcome_name = row["outcome_name"].strip()
        mis_value = _to_float(row["mis_value"], "mis_value") + adjustment
        observed = _to_float(row["observed_prediction"], "observed_prediction") + adjustment
        counterfactual = _to_float(row["counterfactual_prediction"], "counterfactual_prediction")

        mean, std = self.mis_stats.get(outcome_name, (0.0, 1.0))
        mis_z = (mis_value - mean) / std if std > 0 else 0.0

        i50_low = _to_float(row["interval_50_low"], "interval_50_low") + adjustment
        i50_high = _to_float(row["interval_50_high"], "interval_50_high") + adjustment
        i90_low = _to_float(row["interval_90_low"], "interval_90_low") + adjustment
        i90_high = _to_float(row["interval_90_high"], "interval_90_high") + adjustment

        return {
            "outcome_name": outcome_name,
            "mis_value": round(mis_value, 6),
            "mis_z": round(mis_z, 6),
            "median": round(mis_value, 6),
            "interval_50": _interval(i50_low, i50_high),
            "interval_90": _interval(i90_low, i90_high),
            "low_confidence_flag": row["low_confidence_flag"].strip().lower() == "true",
            "model_version": row["model_version"].strip(),
            "data_version": row["data_version"].strip(),
            "run_timestamp": row["generated_at"].strip(),
            "_observed_prediction": round(observed, 6),
            "_counterfactual_prediction": round(counterfactual, 6),
        }

    def simulate(
        self,
        *,
        team_id: str,
        season: int,
        week: int | None,
        scenario_id: str,
        moves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return canonical team impact and scenario-adjusted estimates."""

        base_rows = self._team_base_rows(team_id=team_id, season=season, week=week)

        team_estimates = [self._build_estimate(row, adjustment=0.0) for row in base_rows]

        scenario_estimates = []
        for row in base_rows:
            outcome = row["outcome_name"].strip()
            adjustment = self._scenario_adjustment(team_id=team_id, outcome_name=outcome, moves=moves)
            scenario_estimates.append(self._build_estimate(row, adjustment=adjustment))

        period = f"week_{base_rows[0]['nfl_week'].strip()}"
        result = {
            "team_impact": {
                "team_id": team_id,
                "season": season,
                "period": period,
                "estimates": [
                    {
                        k: v
                        for k, v in estimate.items()
                        if not k.startswith("_")
                    }
                    for estimate in team_estimates
                ],
            },
            "scenario_output": {
                "scenario_id": scenario_id,
                "team_id": team_id,
                "season": season,
                "applied_moves": moves,
                "estimates": [
                    {
                        k: v
                        for k, v in estimate.items()
                        if not k.startswith("_")
                    }
                    for estimate in scenario_estimates
                ],
            },
        }
        return result
