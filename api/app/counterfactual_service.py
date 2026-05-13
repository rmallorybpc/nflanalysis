#!/usr/bin/env python3
"""Counterfactual simulation service for movement impact scenarios."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OUTCOME_ORDER = ["win_pct", "point_diff_per_game", "offensive_epa_per_play"]
ALLOWED_MOVE_SCOPES = ["same_division", "cross_division", "cross_conference"]
ALLOWED_MOVE_TYPES = {"trade", "free_agency"}
MIN_ROBUST_MOVE_COUNT = 10
MAX_UNKNOWN_SCOPE_SHARE_FOR_STRONG_CLAIM = 0.2
MAX_PLACEBO_P_VALUE_FOR_STRONG_CLAIM = 0.1

TEAM_GEO = {
    "ARI": ("NFC", "West"),
    "ATL": ("NFC", "South"),
    "BAL": ("AFC", "North"),
    "BUF": ("AFC", "East"),
    "CAR": ("NFC", "South"),
    "CHI": ("NFC", "North"),
    "CIN": ("AFC", "North"),
    "CLE": ("AFC", "North"),
    "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"),
    "DET": ("NFC", "North"),
    "GB": ("NFC", "North"),
    "HOU": ("AFC", "South"),
    "IND": ("AFC", "South"),
    "JAX": ("AFC", "South"),
    "KC": ("AFC", "West"),
    "LV": ("AFC", "West"),
    "LAC": ("AFC", "West"),
    "LAR": ("NFC", "West"),
    "MIA": ("AFC", "East"),
    "MIN": ("NFC", "North"),
    "NE": ("AFC", "East"),
    "NO": ("NFC", "South"),
    "NYG": ("NFC", "East"),
    "NYJ": ("AFC", "East"),
    "PHI": ("NFC", "East"),
    "PIT": ("AFC", "North"),
    "SEA": ("NFC", "West"),
    "SF": ("NFC", "West"),
    "TB": ("NFC", "South"),
    "TEN": ("AFC", "South"),
    "WAS": ("NFC", "East"),
}

POSITION_GROUP_FEATURE: dict[str, str] = {
    "offense_skill": "offense_skill_value_delta",
    "offense_line": "offense_line_value_delta",
    "defense_front": "defense_front_value_delta",
    "defense_second_level": "defense_second_level_value_delta",
    "defense_secondary": "defense_secondary_value_delta",
    "special_teams": "special_teams_value_delta",
    "other": "other_value_delta",
}

GEOGRAPHY_FEATURE: dict[str, str] = {
    "same_division": "same_division_inbound_count",
    "cross_division": "cross_division_inbound_count",
    "cross_conference": "cross_conference_inbound_count",
}


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


def _move_scope(from_team: str, to_team: str) -> str:
    from_geo = TEAM_GEO.get(from_team)
    to_geo = TEAM_GEO.get(to_team)
    if from_geo is None or to_geo is None:
        return "unknown"

    from_conf, from_div = from_geo
    to_conf, to_div = to_geo
    if from_conf != to_conf:
        return "cross_conference"
    if from_div != to_div:
        return "cross_division"
    return "same_division"


def _infer_scope_from_destination(to_team: str) -> str:
    """
    For free agency moves with no source team, classify scope by
    the destination team's conference. Cross-conference free agency
    is not meaningful without a source, so assign all one-sided moves
    to 'cross_division' as a conservative default that reflects
    genuine roster change without implying a specific rivalry context.
    Return 'unknown' only if to_team is also missing.
    """
    if not to_team or to_team not in TEAM_GEO:
        return "unknown"
    return "cross_division"


def _resolve_move_scope(from_team: str, to_team: str, explicit_scope: str = "") -> str:
    scope = (explicit_scope or "").strip()
    if scope in GEOGRAPHY_FEATURE:
        return scope
    if from_team and to_team:
        return _move_scope(from_team, to_team)
    if to_team:
        return _infer_scope_from_destination(to_team)
    return "unknown"


@dataclass
class ServiceConfig:
    """Input sources for the counterfactual service."""

    model_outputs: Path = Path("data/processed/model_outputs_hierarchical.csv")
    fallback_outputs: Path = Path("data/processed/model_outputs.csv")
    effects: Path = Path("models/artifacts/hierarchical_effects.csv")
    baseline_coefficients: Path = Path("models/artifacts/baseline_coefficients.csv")
    validation_summary: Path = Path("models/artifacts/pretrend_placebo_summary.csv")
    players: Path = Path("data/processed/player_dimension.csv")
    movement_events: Path = Path("data/processed/movement_events.csv")
    team_week_features: Path = Path("data/processed/team_week_features.csv")
    required_seasons: tuple[int, ...] = ()

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        def env_path(var_name: str, default: Path) -> Path:
            raw = os.getenv(var_name, "").strip()
            return Path(raw) if raw else default

        bundle_env = os.getenv("OFFSEASON_SERVING_BUNDLE", "").strip()
        default_bundle = Path("data/processed/offseason/backfill_2022_2026")
        bundle_path = Path(bundle_env) if bundle_env else default_bundle

        using_bundle = bool(bundle_env) or default_bundle.exists()

        if using_bundle:
            default_model_outputs = bundle_path / "model_outputs_hierarchical.csv"
            default_fallback_outputs = bundle_path / "model_outputs.csv"
            default_players = bundle_path / "player_dimension.csv"
            default_movement = bundle_path / "movement_events.csv"
            default_features = bundle_path / "team_week_features.csv"
            default_effects = Path("models/artifacts/offseason") / bundle_path.name / "hierarchical_effects.csv"
            default_coefs = Path("models/artifacts/offseason") / bundle_path.name / "baseline_coefficients.csv"
            default_validation = Path("models/artifacts/offseason") / bundle_path.name / "pretrend_placebo_summary.csv"
        else:
            default_model_outputs = cls.model_outputs
            default_fallback_outputs = cls.fallback_outputs
            default_players = cls.players
            default_movement = cls.movement_events
            default_features = cls.team_week_features
            default_effects = cls.effects
            default_coefs = cls.baseline_coefficients
            default_validation = cls.validation_summary

        required_raw = os.getenv("OFFSEASON_REQUIRED_SEASONS", "").strip()
        if required_raw:
            required_seasons = tuple(
                int(token.strip())
                for token in required_raw.split(",")
                if token.strip()
            )
        elif using_bundle:
            required_seasons = (2022, 2023, 2024, 2025, 2026)
        else:
            required_seasons = ()

        return cls(
            model_outputs=env_path("MODEL_OUTPUTS_PATH", default_model_outputs),
            fallback_outputs=env_path("FALLBACK_OUTPUTS_PATH", default_fallback_outputs),
            effects=env_path("HIERARCHICAL_EFFECTS_PATH", default_effects),
            baseline_coefficients=env_path("BASELINE_COEFFICIENTS_PATH", default_coefs),
            validation_summary=env_path("PRETREND_PLACEBO_SUMMARY_PATH", default_validation),
            players=env_path("PLAYER_DIMENSION_PATH", default_players),
            movement_events=env_path("MOVEMENT_EVENTS_PATH", default_movement),
            team_week_features=env_path("TEAM_WEEK_FEATURES_PATH", default_features),
            required_seasons=required_seasons,
        )


class CounterfactualService:
    """Loads model artifacts and computes scenario deltas with uncertainty."""

    def __init__(self, config: ServiceConfig | None = None) -> None:
        self.config = config or ServiceConfig.from_env()
        self.model_rows = self._load_model_rows()
        self.player_dim = _read_csv(self.config.players)
        self.effect_map = self._load_effects()
        self.player_group = self._load_player_groups()
        self.baseline_coefs = self._load_baseline_coefs()
        self.validation_diag = self._load_validation_diagnostics()
        self.player_name: dict[str, str] = {}
        for row in self.player_dim:
            player_id = row["player_id"].strip()
            full_name = (row.get("full_name", "") or "").strip()
            self.player_name[player_id] = full_name or player_id
        self.mis_stats = self._build_mis_stats()
        self._validate_required_seasons()

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
        for row in self.player_dim:
            out[row["player_id"].strip()] = (row.get("position_group", "") or "other").strip().lower()
        return out

    def _load_baseline_coefs(
        self,
    ) -> dict[tuple[str, str], float]:
        """
        Load baseline ridge coefficients keyed by
        (outcome_name, feature_name).
        Returns empty dict if the file does not exist or is empty.
        """
        path = self.config.baseline_coefficients
        if not path.exists():
            return {}
        out: dict[tuple[str, str], float] = {}
        for row in _read_csv(path):
            outcome = row.get("outcome_name", "").strip()
            feature = row.get("feature_name", "").strip()
            coef = _to_float(row.get("coefficient", "0"), "coefficient")
            if outcome and feature:
                out[(outcome, feature)] = coef
        return out

    def _load_validation_diagnostics(self) -> dict[str, Any]:
        path = self.config.validation_summary
        if not path.exists():
            return {
                "available": False,
                "placebo_win_pct_p_value": 1.0,
                "placebo_iterations": 0,
                "generated_at": "",
            }

        rows = _read_csv(path)
        p_value: float | None = None
        iterations = 0
        generated_at = ""
        for row in rows:
            if not generated_at:
                generated_at = (row.get("generated_at", "") or "").strip()
            test_name = (row.get("test_name", "") or "").strip()
            outcome_name = (row.get("outcome_name", "") or "").strip()
            statistic_name = (row.get("statistic_name", "") or "").strip()
            if test_name == "placebo" and outcome_name == "win_pct" and statistic_name == "one_sided_p_value":
                p_value = _to_float((row.get("statistic_value", "") or "0").strip(), "statistic_value")
                iterations = int(_to_float((row.get("n_units", "") or "0").strip(), "n_units"))
                break

        return {
            "available": p_value is not None,
            "placebo_win_pct_p_value": round(p_value, 6) if p_value is not None else 1.0,
            "placebo_iterations": iterations,
            "generated_at": generated_at,
        }

    def build_players_payload(self) -> dict[str, Any]:
        """Return list of players for typeahead search."""
        players = []
        for row in self.player_dim:
            player_id = str(row.get("player_id", "")).strip()
            full_name = str(row.get("full_name", "")).strip()
            position = str(row.get("position", "")).strip()
            team_id = str(row.get("team_id", "")).strip()
            if not player_id:
                continue
            players.append(
                {
                    "player_id": player_id,
                    "full_name": full_name or player_id,
                    "position": position,
                    "team_id": team_id,
                }
            )
        players.sort(key=lambda player: player["full_name"])
        return {"players": players, "count": len(players)}

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

    def _available_seasons(self) -> list[int]:
        return sorted({int(row["nfl_season"]) for row in self.model_rows})

    def _validate_required_seasons(self) -> None:
        required = set(self.config.required_seasons)
        if not required:
            return

        available = set(self._available_seasons())
        missing = sorted(required - available)
        if missing:
            raise ValueError(
                "configured serving bundle missing required seasons: "
                f"{missing}; available seasons: {sorted(available)}"
            )

    def _validate_season_available(self, requested_season: int) -> None:
        seasons = self._available_seasons()
        if not seasons:
            raise ValueError("no model outputs available")
        if requested_season not in seasons:
            season_list = ", ".join(str(season) for season in seasons)
            raise ValueError(
                f"data not available for season={requested_season}; available seasons: {season_list}"
            )

    def _build_season_coverage(self, seasons: list[int]) -> list[dict[str, int]]:
        points: list[dict[str, int]] = []
        for season in seasons:
            season_rows = [row for row in self.model_rows if int(row["nfl_season"]) == season]
            if not season_rows:
                continue
            latest_week = max(int(row["nfl_week"]) for row in season_rows)
            latest_rows = [row for row in season_rows if int(row["nfl_week"]) == latest_week]
            team_count = len({row["team_id"].strip() for row in latest_rows if row["outcome_name"].strip() == "win_pct"})
            points.append(
                {
                    "season": season,
                    "latest_week": latest_week,
                    "team_count": team_count,
                }
            )
        return points

    def _move_effect_for_profile(
        self,
        player_id: str,
        to_team: str,
        scope: str,
        outcome: str,
    ) -> float:
        # Reuse the scenario layering so geography comparisons stay consistent.
        player_effect = self.effect_map.get((outcome, "player", player_id), None)
        position_group = self.player_group.get(player_id, "other")
        pos_team_key = f"{position_group}|{to_team}"
        pos_team_effect = self.effect_map.get((outcome, "position_team", pos_team_key), None)

        if player_effect is not None or pos_team_effect is not None:
            raw_effect = (player_effect or 0.0) + (pos_team_effect or 0.0)
        else:
            feature_name = POSITION_GROUP_FEATURE.get(position_group)
            raw_effect = 0.0
            if feature_name:
                coef = self.baseline_coefs.get((outcome, feature_name), 0.0)
                raw_effect = coef * 1.0

        geo_feature_name = GEOGRAPHY_FEATURE.get(scope)
        if geo_feature_name:
            raw_effect += self.baseline_coefs.get((outcome, geo_feature_name), 0.0)

        return abs(raw_effect)

    def _resolve_scope_for_mode(
        self,
        row: dict[str, str],
        *,
        require_known_scope: bool,
        allow_destination_inference: bool,
    ) -> str | None:
        explicit_scope = (row.get("move_scope", "") or "").strip()
        from_team = (row.get("from_team_id", "") or "").strip()
        to_team = (row.get("to_team_id", "") or "").strip()

        if explicit_scope in GEOGRAPHY_FEATURE:
            return explicit_scope

        if from_team and to_team:
            inferred = _move_scope(from_team, to_team)
            return inferred if inferred in GEOGRAPHY_FEATURE else None

        if allow_destination_inference and to_team:
            inferred = _infer_scope_from_destination(to_team)
            return inferred if inferred in GEOGRAPHY_FEATURE else None

        if require_known_scope:
            return None

        return None

    def _mode_strongest_scope_summary(
        self,
        points: list[dict[str, Any]],
        placebo_p_value: float,
        placebo_available: bool,
    ) -> dict[str, Any]:
        win_rows = [
            row for row in points
            if row["outcome_name"] == "win_pct" and int(row.get("move_count", 0)) > 0
        ]
        if len(win_rows) < 2:
            return {
                "strongest_scope": "",
                "strongest_avg_abs_impact": 0.0,
                "strongest_move_count": 0,
                "runner_up_scope": "",
                "runner_up_avg_abs_impact": 0.0,
                "placebo_win_pct_p_value": placebo_p_value,
                "robustness_flag": False,
                "robustness_reason": "insufficient_scope_coverage",
            }

        sorted_rows = sorted(win_rows, key=lambda row: float(row["avg_abs_impact"]), reverse=True)
        top = sorted_rows[0]
        runner_up = sorted_rows[1]

        top_count = int(top["move_count"])
        runner_up_count = int(runner_up["move_count"])
        sample_ok = top_count >= MIN_ROBUST_MOVE_COUNT and runner_up_count >= MIN_ROBUST_MOVE_COUNT
        placebo_ok = placebo_available and placebo_p_value <= MAX_PLACEBO_P_VALUE_FOR_STRONG_CLAIM
        robust = sample_ok and placebo_ok

        if not sample_ok:
            reason = "low_sample"
        elif not placebo_available:
            reason = "missing_placebo"
        elif not placebo_ok:
            reason = "placebo_not_significant"
        else:
            reason = "ok"

        return {
            "strongest_scope": str(top["move_scope"]),
            "strongest_avg_abs_impact": float(top["avg_abs_impact"]),
            "strongest_move_count": top_count,
            "runner_up_scope": str(runner_up["move_scope"]),
            "runner_up_avg_abs_impact": float(runner_up["avg_abs_impact"]),
            "placebo_win_pct_p_value": placebo_p_value,
            "robustness_flag": robust,
            "robustness_reason": reason,
        }

    def _build_geography_profile_mode(
        self,
        movement_rows: list[dict[str, str]],
        seasons: list[int],
        *,
        mode: str,
        label: str,
        include_move_types: set[str],
        require_known_scope: bool,
        allow_destination_inference: bool,
        placebo_p_value: float,
        placebo_available: bool,
    ) -> dict[str, Any]:
        buckets: dict[tuple[str, str], list[float]] = {
            (scope, outcome): []
            for scope in ALLOWED_MOVE_SCOPES
            for outcome in OUTCOME_ORDER
        }

        included_events = 0
        excluded_events = 0
        allowed_seasons = {str(season) for season in seasons}
        for row in movement_rows:
            if row.get("nfl_season", "").strip() not in allowed_seasons:
                continue

            move_type = row.get("move_type", "").strip()
            if move_type not in include_move_types:
                continue

            scope = self._resolve_scope_for_mode(
                row,
                require_known_scope=require_known_scope,
                allow_destination_inference=allow_destination_inference,
            )
            if scope not in ALLOWED_MOVE_SCOPES:
                excluded_events += 1
                continue

            to_team = (row.get("to_team_id", "") or "").strip()
            if not to_team:
                excluded_events += 1
                continue

            included_events += 1
            player_id = (row.get("player_id", "") or "").strip()
            for outcome in OUTCOME_ORDER:
                effect = self._move_effect_for_profile(player_id, to_team, scope, outcome)
                buckets[(scope, outcome)].append(effect)

        points: list[dict[str, Any]] = []
        for scope in ALLOWED_MOVE_SCOPES:
            for outcome in OUTCOME_ORDER:
                values = buckets[(scope, outcome)]
                count = len(values)
                avg_abs = sum(values) / count if count else 0.0
                points.append(
                    {
                        "move_scope": scope,
                        "outcome_name": outcome,
                        "move_count": count,
                        "avg_abs_impact": round(avg_abs, 6),
                    }
                )

        return {
            "mode": mode,
            "label": label,
            "included_event_count": included_events,
            "excluded_event_count": excluded_events,
            "points": points,
            "win_pct_summary": self._mode_strongest_scope_summary(points, placebo_p_value, placebo_available),
        }

    def _build_geography_claim_policy(
        self,
        diagnostics: dict[str, int | float],
        sensitivity_profiles: list[dict[str, Any]],
        validation_diag: dict[str, Any],
    ) -> dict[str, Any]:
        reasons: list[str] = []

        unknown_share = float(diagnostics.get("unknown_scope_share", 0.0) or 0.0)
        unknown_ok = unknown_share <= MAX_UNKNOWN_SCOPE_SHARE_FOR_STRONG_CLAIM
        if not unknown_ok:
            reasons.append("high_unknown_scope_share")

        by_mode = {str(profile.get("mode", "")): profile for profile in sensitivity_profiles}
        known_summary = ((by_mode.get("known_scope_only") or {}).get("win_pct_summary") or {})
        trades_summary = ((by_mode.get("trades_only") or {}).get("win_pct_summary") or {})
        if not bool(known_summary.get("robustness_flag", False)):
            reasons.append("known_scope_not_robust")
        if not bool(trades_summary.get("robustness_flag", False)):
            reasons.append("trades_not_robust")

        placebo_available = bool(validation_diag.get("available", False))
        placebo_p_value = float(validation_diag.get("placebo_win_pct_p_value", 1.0) or 1.0)
        if not placebo_available:
            reasons.append("missing_placebo")
        elif placebo_p_value > MAX_PLACEBO_P_VALUE_FOR_STRONG_CLAIM:
            reasons.append("placebo_not_significant")

        can_make_strong_claim = len(reasons) == 0
        return {
            "can_make_strong_claim": can_make_strong_claim,
            "reasons": ["ok"] if can_make_strong_claim else reasons,
            "min_robust_move_count": MIN_ROBUST_MOVE_COUNT,
            "max_unknown_scope_share": MAX_UNKNOWN_SCOPE_SHARE_FOR_STRONG_CLAIM,
            "max_placebo_p_value": MAX_PLACEBO_P_VALUE_FOR_STRONG_CLAIM,
        }

    def _build_geography_diagnostics(
        self,
        movement_rows: list[dict[str, str]],
        seasons: list[int],
    ) -> dict[str, int | float]:
        allowed_seasons = {str(season) for season in seasons}
        total_events = 0
        missing_from_team = 0
        destination_only_events = 0
        unknown_scope_events = 0

        for row in movement_rows:
            if row.get("nfl_season", "").strip() not in allowed_seasons:
                continue

            move_type = row.get("move_type", "").strip()
            if move_type not in ALLOWED_MOVE_TYPES:
                continue

            total_events += 1
            from_team = (row.get("from_team_id", "") or "").strip()
            to_team = (row.get("to_team_id", "") or "").strip()
            explicit_scope = (row.get("move_scope", "") or "").strip()

            if not from_team:
                missing_from_team += 1
            if to_team and not from_team:
                destination_only_events += 1

            if explicit_scope in GEOGRAPHY_FEATURE:
                continue
            if from_team and to_team and _move_scope(from_team, to_team) in GEOGRAPHY_FEATURE:
                continue
            unknown_scope_events += 1

        unknown_share = (unknown_scope_events / total_events) if total_events else 0.0
        return {
            "total_events": total_events,
            "unknown_scope_events": unknown_scope_events,
            "unknown_scope_share": round(unknown_share, 6),
            "missing_from_team_events": missing_from_team,
            "destination_only_events": destination_only_events,
        }

    def _build_geography_impact_profile(self, seasons: list[int]) -> list[dict[str, Any]]:
        movement_rows = _read_csv(self.config.movement_events)
        placebo_p_value = float(self.validation_diag.get("placebo_win_pct_p_value", 1.0) or 1.0)
        placebo_available = bool(self.validation_diag.get("available", False))
        mode_profile = self._build_geography_profile_mode(
            movement_rows,
            seasons,
            mode="all_events",
            label="All events",
            include_move_types=ALLOWED_MOVE_TYPES,
            require_known_scope=False,
            allow_destination_inference=True,
            placebo_p_value=placebo_p_value,
            placebo_available=placebo_available,
        )
        return mode_profile["points"]

    def _build_geography_sensitivity_profiles(
        self,
        seasons: list[int],
        validation_diag: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, int | float], dict[str, Any]]:
        movement_rows = _read_csv(self.config.movement_events)
        placebo_p_value = float(validation_diag.get("placebo_win_pct_p_value", 1.0) or 1.0)
        placebo_available = bool(validation_diag.get("available", False))
        profiles = [
            self._build_geography_profile_mode(
                movement_rows,
                seasons,
                mode="all_events",
                label="All events",
                include_move_types=ALLOWED_MOVE_TYPES,
                require_known_scope=False,
                allow_destination_inference=True,
                placebo_p_value=placebo_p_value,
                placebo_available=placebo_available,
            ),
            self._build_geography_profile_mode(
                movement_rows,
                seasons,
                mode="known_scope_only",
                label="Known scope only",
                include_move_types=ALLOWED_MOVE_TYPES,
                require_known_scope=True,
                allow_destination_inference=False,
                placebo_p_value=placebo_p_value,
                placebo_available=placebo_available,
            ),
            self._build_geography_profile_mode(
                movement_rows,
                seasons,
                mode="trades_only",
                label="Trades only",
                include_move_types={"trade"},
                require_known_scope=True,
                allow_destination_inference=False,
                placebo_p_value=placebo_p_value,
                placebo_available=placebo_available,
            ),
        ]
        diagnostics = self._build_geography_diagnostics(movement_rows, seasons)
        policy = self._build_geography_claim_policy(diagnostics, profiles, validation_diag)
        return profiles, diagnostics, policy

    def _team_base_rows(self, team_id: str, season: int, week: int | None) -> list[dict[str, str]]:
        self._validate_season_available(season)
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

    def _scenario_adjustment(
        self,
        team_id: str,
        outcome_name: str,
        moves: list[dict[str, Any]],
    ) -> float:
        adjustment = 0.0
        for move in moves:
            player_id = str(move.get("player_id", "")).strip()
            action = str(move.get("action", "")).strip().lower()
            from_team = str(move.get("from_team_id", "")).strip()
            to_team = str(move.get("to_team_id", "")).strip()
            move_scope = _resolve_move_scope(from_team, to_team, str(move.get("move_scope", "")))

            direction = 0.0
            if action == "add" and to_team == team_id:
                direction = 1.0
            elif action == "remove" and from_team == team_id:
                direction = -1.0
            else:
                continue

            # Layer 1: player-level hierarchical effect
            player_effect = self.effect_map.get(
                (outcome_name, "player", player_id), None
            )

            # Layer 2: position-team hierarchical effect
            position_group = self.player_group.get(player_id, "other")
            pos_team_key = f"{position_group}|{team_id}"
            pos_team_effect = self.effect_map.get(
                (outcome_name, "position_team", pos_team_key), None
            )

            if player_effect is not None:
                adjustment += direction * player_effect
            elif pos_team_effect is not None:
                adjustment += direction * pos_team_effect
            else:
                # Layer 3: fallback to baseline coefficient
                # Use the position group value delta coefficient as a
                # proxy for the marginal impact of one roster move in
                # that position group
                feature_name = POSITION_GROUP_FEATURE.get(
                    position_group
                )
                if feature_name:
                    coef = self.baseline_coefs.get(
                        (outcome_name, feature_name), 0.0
                    )
                    adjustment += direction * coef * 1.0

                geo_feature_name = GEOGRAPHY_FEATURE.get(move_scope)
                if geo_feature_name:
                    geo_coef = self.baseline_coefs.get((outcome_name, geo_feature_name), 0.0)
                    adjustment += direction * geo_coef

        return adjustment

    def build_overview_payload(self, season: int) -> dict[str, Any]:
        """Build overview dashboard payload using canonical schema fields."""

        self._validate_season_available(season)
        season_rows = [row for row in self.model_rows if int(row["nfl_season"]) == season]
        if not season_rows:
            raise ValueError(f"no model outputs found for season={season}")

        latest_week = max(int(row["nfl_week"]) for row in season_rows)
        latest_rows = [row for row in season_rows if int(row["nfl_week"]) == latest_week]
        rank_rows = [row for row in latest_rows if row["outcome_name"].strip() == "win_pct"]
        rank_rows.sort(key=lambda row: _to_float(row["mis_value"], "mis_value"), reverse=True)

        deduped_rank_rows = []
        seen_teams: set[str] = set()
        for row in rank_rows:
            team_id = row["team_id"].strip()
            if team_id in seen_teams:
                continue
            seen_teams.add(team_id)
            deduped_rank_rows.append(row)

        if not deduped_rank_rows:
            raise ValueError("no ranking rows available for win_pct outcome")

        def to_card(row: dict[str, str]) -> dict[str, Any]:
            return {
                "team_id": row["team_id"].strip(),
                "outcome_name": row["outcome_name"].strip(),
                "mis_value": round(_to_float(row["mis_value"], "mis_value"), 6),
                "mis_z": round(_to_float(row["mis_z"], "mis_z"), 6),
                "interval_90": _interval(
                    _to_float(row["interval_90_low"], "interval_90_low"),
                    _to_float(row["interval_90_high"], "interval_90_high"),
                ),
                "low_confidence_flag": row["low_confidence_flag"].strip().lower() == "true",
                "model_version": row["model_version"].strip(),
                "data_version": row["data_version"].strip(),
            }

        league_net_mis = sum(_to_float(row["mis_value"], "mis_value") for row in deduped_rank_rows)
        high_conf_count = sum(1 for row in deduped_rank_rows if row["low_confidence_flag"].strip().lower() == "false")
        high_conf_share = high_conf_count / len(deduped_rank_rows)

        ranking_points = []
        for index, row in enumerate(deduped_rank_rows, start=1):
            ranking_points.append(
                {
                    "rank": index,
                    "team_id": row["team_id"].strip(),
                    "mis_value": round(_to_float(row["mis_value"], "mis_value"), 6),
                    "mis_z": round(_to_float(row["mis_z"], "mis_z"), 6),
                }
            )

        bins = [(-99.0, -1.0, "<= -1.0"), (-1.0, -0.3, "-1.0 to -0.3"), (-0.3, 0.3, "-0.3 to 0.3"), (0.3, 1.0, "0.3 to 1.0"), (1.0, 99.0, ">= 1.0")]
        distribution: dict[tuple[str, str], int] = {}
        for row in latest_rows:
            outcome = row["outcome_name"].strip()
            mis_z = _to_float(row["mis_z"], "mis_z")
            label = ">= 1.0"
            for low, high, bin_label in bins:
                if low <= mis_z < high or (bin_label == ">= 1.0" and mis_z >= 1.0):
                    label = bin_label
                    break
            key = (outcome, label)
            distribution[key] = distribution.get(key, 0) + 1

        dist_points = [
            {"outcome_name": outcome, "bin_label": label, "count": count}
            for (outcome, label), count in sorted(distribution.items())
        ]

        available_seasons = self._available_seasons()
        season_coverage = self._build_season_coverage(available_seasons)
        geography_profile = self._build_geography_impact_profile([season])
        geography_sensitivity_profiles, geography_quality, geography_claim_policy = self._build_geography_sensitivity_profiles(
            [season],
            self.validation_diag,
        )
        season_events = [
            row
            for row in _read_csv(self.config.movement_events)
            if int(row.get("nfl_season", "0") or 0) == season
        ]
        move_type_counts = {"trade": 0, "free_agency": 0}
        for row in season_events:
            move_type = row.get("move_type", "").strip()
            if move_type in move_type_counts:
                move_type_counts[move_type] += 1
        anomaly_tags = sorted(
            {
                row.get("season_anomaly", "").strip()
                for row in season_events
                if row.get("season_anomaly", "").strip()
            }
        )

        return {
            "season": season,
            "generated_at": deduped_rank_rows[0]["generated_at"].strip(),
            "scope": {
                "season_range": {
                    "start": available_seasons[0],
                    "end": available_seasons[-1],
                },
                "season_count": len(available_seasons),
                "team_count": len({row["team_id"].strip() for row in self.model_rows}),
                "included_move_types": ["trade", "free_agency"],
                "move_type_counts": move_type_counts,
                "outcomes": OUTCOME_ORDER,
                "geography_dimensions": ["team", "division", "conference"],
                "geography_data_quality": geography_quality,
                "validation_diagnostics": self.validation_diag,
                "geography_claim_policy": geography_claim_policy,
                "season_anomaly": anomaly_tags,
            },
            "cards": {
                "top_positive_team": to_card(deduped_rank_rows[0]),
                "top_negative_team": to_card(deduped_rank_rows[-1]),
                "league_net_mis": round(league_net_mis, 6),
                "high_confidence_share": round(high_conf_share, 6),
            },
            "charts": {
                "league_ranking": ranking_points,
                "outcome_distribution": dist_points,
                "season_coverage": season_coverage,
                "geography_impact_profile": geography_profile,
                "geography_sensitivity_profiles": geography_sensitivity_profiles,
            },
        }

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

    def build_team_detail_payload(self, team_id: str, season: int) -> dict[str, Any]:
        """Build team detail dashboard payload using schema contract fields."""

        self._validate_season_available(season)
        team_rows = [
            row
            for row in self.model_rows
            if row["team_id"].strip() == team_id and int(row["nfl_season"]) == season
        ]
        if not team_rows:
            raise ValueError(f"no model outputs found for team_id={team_id} season={season}")

        team_rows.sort(key=lambda row: int(row["nfl_week"]))
        latest_week = int(team_rows[-1]["nfl_week"])
        latest_rows = [row for row in team_rows if int(row["nfl_week"]) == latest_week]

        win_pct_row = next((row for row in latest_rows if row["outcome_name"].strip() == "win_pct"), latest_rows[0])

        features = _read_csv(self.config.team_week_features)
        feature_row = next(
            (
                row
                for row in features
                if row["team_id"].strip() == team_id
                and int(row["nfl_season"]) == season
                and int(row["nfl_week"]) == latest_week
            ),
            None,
        )
        if feature_row is None:
            raise ValueError(f"missing feature row for team_id={team_id} season={season} week={latest_week}")

        movement_rows = _read_csv(self.config.movement_events)
        relevant_moves = []
        team_events = []
        for row in movement_rows:
            if row.get("season_phase", "").strip() != "regular":
                continue
            if row.get("nfl_season", "").strip() != str(season):
                continue
            if row.get("to_team_id", "").strip() != team_id and row.get("from_team_id", "").strip() != team_id:
                continue

            team_events.append(row)

            sign = 1.0 if row.get("to_team_id", "").strip() == team_id else -1.0
            player_id = row.get("player_id", "").strip()
            # Layer 1: player-level hierarchical effect
            player_effect = self.effect_map.get(("win_pct", "player", player_id), None)

            # Layer 2: position-team hierarchical effect
            position_group = self.player_group.get(player_id, "other")
            pos_team_key = f"{position_group}|{team_id}"
            pos_team_effect = self.effect_map.get(("win_pct", "position_team", pos_team_key), None)

            if player_effect is not None or pos_team_effect is not None:
                raw_impact = (player_effect or 0.0) + (pos_team_effect or 0.0)
            else:
                feature_name = POSITION_GROUP_FEATURE.get(position_group)
                raw_impact = 0.0
                if feature_name:
                    coef = self.baseline_coefs.get(("win_pct", feature_name), 0.0)
                    raw_impact = coef * 1.0

            scope = _resolve_move_scope(
                row.get("from_team_id", "").strip(),
                row.get("to_team_id", "").strip(),
                row.get("move_scope", ""),
            )
            geo_feature_name = GEOGRAPHY_FEATURE.get(scope)
            if geo_feature_name:
                raw_impact += self.baseline_coefs.get(("win_pct", geo_feature_name), 0.0)

            impact = sign * raw_impact

            relevant_moves.append(
                {
                    "move_id": row.get("move_id", "").strip(),
                    "event_date": row.get("event_date", "").strip(),
                    "effective_date": row.get("effective_date", "").strip(),
                    "nfl_week": int(row.get("nfl_week", "0") or "0"),
                    "move_type": row.get("move_type", "").strip(),
                    "player_id": player_id,
                    "player_name": self.player_name.get(player_id, player_id),
                    "from_team_id": row.get("from_team_id", "").strip(),
                    "to_team_id": row.get("to_team_id", "").strip(),
                    "move_scope": _resolve_move_scope(
                        row.get("from_team_id", "").strip(),
                        row.get("to_team_id", "").strip(),
                        row.get("move_scope", ""),
                    ),
                    "impact_estimate": round(impact, 6),
                    "contract_aav": row.get("contract_aav", ""),
                    "contract_total": row.get("contract_total", ""),
                    "contract_years": row.get("contract_years", ""),
                }
            )

        relevant_moves.sort(key=lambda row: (row["nfl_week"], row["event_date"], row["move_id"]))

        trend_rows = [
            row
            for row in team_rows
            if row["outcome_name"].strip() in {"win_pct", "point_diff_per_game", "offensive_epa_per_play"}
        ]
        trend_rows.sort(key=lambda row: (int(row["nfl_week"]), row["outcome_name"]))

        mis_trend = [
            {
                "nfl_week": int(row["nfl_week"]),
                "outcome_name": row["outcome_name"].strip(),
                "mis_value": round(_to_float(row["mis_value"], "mis_value"), 6),
                "interval_90": _interval(
                    _to_float(row["interval_90_low"], "interval_90_low"),
                    _to_float(row["interval_90_high"], "interval_90_high"),
                ),
            }
            for row in trend_rows
        ]

        position_group_delta = [
            {"position_group": "offense_skill", "value_delta": round(_to_float(feature_row["offense_skill_value_delta"], "offense_skill_value_delta"), 6)},
            {"position_group": "offense_line", "value_delta": round(_to_float(feature_row["offense_line_value_delta"], "offense_line_value_delta"), 6)},
            {"position_group": "defense_front", "value_delta": round(_to_float(feature_row["defense_front_value_delta"], "defense_front_value_delta"), 6)},
            {"position_group": "defense_second_level", "value_delta": round(_to_float(feature_row["defense_second_level_value_delta"], "defense_second_level_value_delta"), 6)},
            {"position_group": "defense_secondary", "value_delta": round(_to_float(feature_row["defense_secondary_value_delta"], "defense_secondary_value_delta"), 6)},
            {"position_group": "special_teams", "value_delta": round(_to_float(feature_row["special_teams_value_delta"], "special_teams_value_delta"), 6)},
            {"position_group": "other", "value_delta": round(_to_float(feature_row["other_value_delta"], "other_value_delta"), 6)},
        ]

        current_mis = {
            "outcome_name": win_pct_row["outcome_name"].strip(),
            "mis_value": round(_to_float(win_pct_row["mis_value"], "mis_value"), 6),
            "mis_z": round(_to_float(win_pct_row["mis_z"], "mis_z"), 6),
            "interval_50": _interval(
                _to_float(win_pct_row["interval_50_low"], "interval_50_low"),
                _to_float(win_pct_row["interval_50_high"], "interval_50_high"),
            ),
            "interval_90": _interval(
                _to_float(win_pct_row["interval_90_low"], "interval_90_low"),
                _to_float(win_pct_row["interval_90_high"], "interval_90_high"),
            ),
            "low_confidence_flag": win_pct_row["low_confidence_flag"].strip().lower() == "true",
            "model_version": win_pct_row["model_version"].strip(),
            "data_version": win_pct_row["data_version"].strip(),
        }

        anomaly_tags = sorted(
            {
                row.get("season_anomaly", "").strip()
                for row in team_events
                if row.get("season_anomaly", "").strip()
            }
        )

        return {
            "team_id": team_id,
            "season": season,
            "generated_at": win_pct_row["generated_at"].strip(),
            "season_anomaly": anomaly_tags,
            "cards": {
                "current_mis": current_mis,
                "inbound_move_count": int(_to_float(feature_row["inbound_move_count"], "inbound_move_count")),
                "outbound_move_count": int(_to_float(feature_row["outbound_move_count"], "outbound_move_count")),
                "net_position_value_delta": round(_to_float(feature_row["position_value_delta"], "position_value_delta"), 6),
            },
            "timeline": relevant_moves,
            "charts": {
                "mis_trend": mis_trend,
                "position_group_delta": position_group_delta,
            },
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

    def build_scenario_sandbox_payload(
        self,
        *,
        team_id: str,
        season: int,
        week: int | None,
        scenario_id: str,
        moves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build scenario sandbox payload with baseline/scenario estimates and deltas."""

        result = self.simulate(
            team_id=team_id,
            season=season,
            week=week,
            scenario_id=scenario_id,
            moves=moves,
        )

        baseline = result["team_impact"]["estimates"]
        scenario = result["scenario_output"]["estimates"]
        baseline_by_outcome = {row["outcome_name"]: row for row in baseline}
        scenario_by_outcome = {row["outcome_name"]: row for row in scenario}

        delta_summary = []
        for outcome in OUTCOME_ORDER:
            if outcome not in baseline_by_outcome or outcome not in scenario_by_outcome:
                continue

            b = baseline_by_outcome[outcome]
            s = scenario_by_outcome[outcome]
            delta = float(s["mis_value"]) - float(b["mis_value"])
            d90_low = float(s["interval_90"]["low"]) - float(b["interval_90"]["low"])
            d90_high = float(s["interval_90"]["high"]) - float(b["interval_90"]["high"])

            if delta > 1e-9:
                direction = "positive"
            elif delta < -1e-9:
                direction = "negative"
            else:
                direction = "neutral"

            delta_summary.append(
                {
                    "outcome_name": outcome,
                    "mis_delta": round(delta, 6),
                    "direction": direction,
                    "interval_90_delta": _interval(d90_low, d90_high),
                }
            )

        run_timestamp = scenario[0]["run_timestamp"] if scenario else baseline[0]["run_timestamp"]
        return {
            "scenario_id": scenario_id,
            "team_id": team_id,
            "season": season,
            "period": result["team_impact"]["period"],
            "applied_moves": moves,
            "baseline_estimates": baseline,
            "scenario_estimates": scenario,
            "delta_summary": delta_summary,
            "generated_at": run_timestamp,
        }
