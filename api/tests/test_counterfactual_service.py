#!/usr/bin/env python3
"""Unit tests for the counterfactual simulation service."""

from __future__ import annotations

import unittest

from api.app.counterfactual_service import CounterfactualService


class CounterfactualServiceTests(unittest.TestCase):
    """Validate canonical response contract and scenario deltas."""

    def setUp(self) -> None:
        self.service = CounterfactualService()

    def test_simulate_returns_schema_fields(self) -> None:
        response = self.service.simulate(
            team_id="BUF",
            season=2024,
            week=6,
            scenario_id="test-baseline",
            moves=[],
        )

        self.assertIn("team_impact", response)
        self.assertIn("scenario_output", response)

        team_impact = response["team_impact"]
        scenario = response["scenario_output"]

        self.assertEqual(team_impact["team_id"], "BUF")
        self.assertEqual(team_impact["season"], 2024)
        self.assertTrue(team_impact["period"].startswith("week_"))

        self.assertEqual(scenario["scenario_id"], "test-baseline")
        self.assertEqual(scenario["team_id"], "BUF")
        self.assertEqual(scenario["season"], 2024)
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
            team_id="BUF",
            season=2024,
            week=6,
            scenario_id="baseline",
            moves=[],
        )
        with_move = self.service.simulate(
            team_id="BUF",
            season=2024,
            week=6,
            scenario_id="add-p003",
            moves=[
                {
                    "move_id": "custom_001",
                    "player_id": "p_003",
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
        payload = self.service.build_overview_payload(season=2024)

        self.assertEqual(payload["season"], 2024)
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
        payload = self.service.build_team_detail_payload(team_id="BUF", season=2024)

        self.assertEqual(payload["team_id"], "BUF")
        self.assertEqual(payload["season"], 2024)
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
            team_id="BUF",
            season=2024,
            week=6,
            scenario_id="sandbox-add-p003",
            moves=[
                {
                    "move_id": "custom_002",
                    "player_id": "p_003",
                    "from_team_id": "NYJ",
                    "to_team_id": "BUF",
                    "move_type": "trade",
                    "action": "add",
                }
            ],
        )

        self.assertEqual(payload["scenario_id"], "sandbox-add-p003")
        self.assertEqual(payload["team_id"], "BUF")
        self.assertEqual(payload["season"], 2024)
        self.assertTrue(payload["period"].startswith("week_"))

        self.assertGreaterEqual(len(payload["baseline_estimates"]), 1)
        self.assertGreaterEqual(len(payload["scenario_estimates"]), 1)
        self.assertGreaterEqual(len(payload["delta_summary"]), 1)

        delta_by_outcome = {row["outcome_name"]: row for row in payload["delta_summary"]}
        self.assertEqual(delta_by_outcome["win_pct"]["direction"], "positive")
        self.assertGreater(delta_by_outcome["win_pct"]["mis_delta"], 0)

    def test_overview_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "data not available for season=2026"):
            self.service.build_overview_payload(season=2026)

    def test_team_detail_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "data not available for season=2026"):
            self.service.build_team_detail_payload(team_id="BUF", season=2026)

    def test_simulate_raises_when_season_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "data not available for season=2026"):
            self.service.simulate(
                team_id="BUF",
                season=2026,
                week=6,
                scenario_id="missing-year",
                moves=[],
            )


if __name__ == "__main__":
    unittest.main()
