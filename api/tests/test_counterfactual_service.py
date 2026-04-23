#!/usr/bin/env python3
"""Unit tests for the counterfactual simulation service."""

from __future__ import annotations

import unittest

from api.app.counterfactual_service import CounterfactualService


class CounterfactualServiceTests(unittest.TestCase):
    """Validate canonical response contract and scenario deltas."""

    def setUp(self) -> None:
        self.service = CounterfactualService()
        self.season = max(int(row["nfl_season"]) for row in self.service.model_rows)
        self.team_id = "BUF"
        self.test_player_id = "p_003"
        self.week = max(
            int(row["nfl_week"])
            for row in self.service.model_rows
            if row["team_id"].strip() == self.team_id and int(row["nfl_season"]) == self.season
        )
        available = {int(row["nfl_season"]) for row in self.service.model_rows}
        self.missing_season = max(available) + 1

        # Keep move-impact tests deterministic even when artifact effects are all zeros.
        self.service.effect_map[("win_pct", "player", self.test_player_id)] = 0.05

    def test_simulate_returns_schema_fields(self) -> None:
        response = self.service.simulate(
            team_id=self.team_id,
            season=self.season,
            week=self.week,
            scenario_id="test-baseline",
            moves=[],
        )

        self.assertIn("team_impact", response)
        self.assertIn("scenario_output", response)

        team_impact = response["team_impact"]
        scenario = response["scenario_output"]

        self.assertEqual(team_impact["team_id"], self.team_id)
        self.assertEqual(team_impact["season"], self.season)
        self.assertTrue(team_impact["period"].startswith("week_"))

        self.assertEqual(scenario["scenario_id"], "test-baseline")
        self.assertEqual(scenario["team_id"], self.team_id)
        self.assertEqual(scenario["season"], self.season)
        self.assertEqual(scenario["applied_moves"], [])

        for estimate in scenario["estimates"]:
            self.assertIn("outcome_name", estimate)
            self.assertIn("mis_value", estimate)
            self.assertIn("mis_z", estimate)
            self.assertIn("median", estimate)
            self.assertIn("interval_50", estimate)
            self.assertIn("interval_90", estimate)
            self.assertIn("low_confidence_flag", estimate)
            self.assertIn("model_version", estimate)
            self.assertIn("data_version", estimate)
            self.assertIn("run_timestamp", estimate)

    def test_add_move_changes_scenario_estimate(self) -> None:
        baseline = self.service.simulate(
            team_id=self.team_id,
            season=self.season,
            week=self.week,
            scenario_id="baseline",
            moves=[],
        )
        with_move = self.service.simulate(
            team_id=self.team_id,
            season=self.season,
            week=self.week,
            scenario_id="add-p003",
            moves=[
                {
                    "move_id": "custom_001",
                    "player_id": self.test_player_id,
                    "from_team_id": "NYJ",
                    "to_team_id": "BUF",
                    "move_type": "trade",
                    "action": "add",
                }
            ],
        )

        baseline_by_outcome = {
            row["outcome_name"]: row for row in baseline["scenario_output"]["estimates"]
        }
        with_move_by_outcome = {
            row["outcome_name"]: row for row in with_move["scenario_output"]["estimates"]
        }

        self.assertGreater(
            with_move_by_outcome["win_pct"]["mis_value"],
            baseline_by_outcome["win_pct"]["mis_value"],
        )

    def test_overview_payload_contains_required_sections(self) -> None:
        payload = self.service.build_overview_payload(season=self.season)

        self.assertEqual(payload["season"], self.season)
        self.assertIn("generated_at", payload)
        self.assertIn("scope", payload)
        self.assertIn("cards", payload)
        self.assertIn("charts", payload)

        scope = payload["scope"]
        self.assertIn("season_range", scope)
        self.assertIn("season_count", scope)
        self.assertIn("team_count", scope)
        self.assertIn("included_move_types", scope)
        self.assertIn("move_type_counts", scope)
        self.assertIn("outcomes", scope)
        self.assertIn("geography_dimensions", scope)

        cards = payload["cards"]
        self.assertIn("top_positive_team", cards)
        self.assertIn("top_negative_team", cards)
        self.assertIn("league_net_mis", cards)
        self.assertIn("high_confidence_share", cards)

        charts = payload["charts"]
        self.assertGreaterEqual(len(charts["league_ranking"]), 1)
        self.assertGreaterEqual(len(charts["outcome_distribution"]), 1)
        self.assertGreaterEqual(len(charts["season_coverage"]), 1)
        self.assertGreaterEqual(len(charts["geography_impact_profile"]), 1)

    def test_team_detail_payload_contains_required_sections(self) -> None:
        payload = self.service.build_team_detail_payload(team_id=self.team_id, season=self.season)

        self.assertEqual(payload["team_id"], self.team_id)
        self.assertEqual(payload["season"], self.season)
        self.assertIn("generated_at", payload)
        self.assertIn("cards", payload)
        self.assertIn("timeline", payload)
        self.assertIn("charts", payload)

        cards = payload["cards"]
        self.assertIn("current_mis", cards)
        self.assertIn("inbound_move_count", cards)
        self.assertIn("outbound_move_count", cards)
        self.assertIn("net_position_value_delta", cards)

        charts = payload["charts"]
        self.assertGreaterEqual(len(charts["mis_trend"]), 1)
        self.assertGreaterEqual(len(charts["position_group_delta"]), 1)

    def test_scenario_sandbox_payload_contains_delta_summary(self) -> None:
        payload = self.service.build_scenario_sandbox_payload(
            team_id=self.team_id,
            season=self.season,
            week=self.week,
            scenario_id="sandbox-add-p003",
            moves=[
                {
                    "move_id": "custom_002",
                    "player_id": self.test_player_id,
                    "from_team_id": "NYJ",
                    "to_team_id": "BUF",
                    "move_type": "trade",
                    "action": "add",
                }
            ],
        )

        self.assertEqual(payload["scenario_id"], "sandbox-add-p003")
        self.assertEqual(payload["team_id"], self.team_id)
        self.assertEqual(payload["season"], self.season)
        self.assertTrue(payload["period"].startswith("week_"))

        self.assertGreaterEqual(len(payload["baseline_estimates"]), 1)
        self.assertGreaterEqual(len(payload["scenario_estimates"]), 1)
        self.assertGreaterEqual(len(payload["delta_summary"]), 1)

        delta_by_outcome = {row["outcome_name"]: row for row in payload["delta_summary"]}
        self.assertEqual(delta_by_outcome["win_pct"]["direction"], "positive")
        self.assertGreater(delta_by_outcome["win_pct"]["mis_delta"], 0)

    def test_overview_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, f"data not available for season={self.missing_season}"):
            self.service.build_overview_payload(season=self.missing_season)

    def test_team_detail_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, f"data not available for season={self.missing_season}"):
            self.service.build_team_detail_payload(team_id=self.team_id, season=self.missing_season)

    def test_simulate_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, f"data not available for season={self.missing_season}"):
            self.service.simulate(
                team_id=self.team_id,
                season=self.missing_season,
                week=self.week,
                scenario_id="missing-year",
                moves=[],
            )


if __name__ == "__main__":
    unittest.main()
