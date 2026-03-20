#!/usr/bin/env python3
"""Contract checks for overview dashboard payload fixture."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class OverviewPayloadTests(unittest.TestCase):
    """Validate sample payload shape expected by the overview UI."""

    def test_sample_payload_has_required_fields(self) -> None:
        path = Path("dashboard/public/overview.sample.json")
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        self.assertIn("season", payload)
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


if __name__ == "__main__":
    unittest.main()
