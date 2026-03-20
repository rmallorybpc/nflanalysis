#!/usr/bin/env python3
"""Contract checks for scenario sandbox payload fixture."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class ScenarioSandboxPayloadTests(unittest.TestCase):
    """Validate scenario sandbox payload shape expected by UI."""

    def test_sample_payload_has_required_sections(self) -> None:
        path = Path("dashboard/public/scenario-sandbox.sample.json")
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        required = {
            "scenario_id",
            "team_id",
            "season",
            "period",
            "applied_moves",
            "baseline_estimates",
            "scenario_estimates",
            "delta_summary",
            "generated_at",
        }
        self.assertTrue(required.issubset(payload.keys()))
        self.assertGreaterEqual(len(payload["baseline_estimates"]), 1)
        self.assertGreaterEqual(len(payload["scenario_estimates"]), 1)
        self.assertGreaterEqual(len(payload["delta_summary"]), 1)


if __name__ == "__main__":
    unittest.main()
