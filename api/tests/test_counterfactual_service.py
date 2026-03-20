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


if __name__ == "__main__":
    unittest.main()
