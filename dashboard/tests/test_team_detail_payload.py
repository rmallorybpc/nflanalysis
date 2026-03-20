#!/usr/bin/env python3
"""Contract checks for team detail dashboard payload fixture."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class TeamDetailPayloadTests(unittest.TestCase):
    """Validate shape expected by team detail page."""

    def test_sample_payload_has_required_sections(self) -> None:
        path = Path("dashboard/public/team-detail.sample.json")
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        self.assertIn("team_id", payload)
        self.assertIn("season", payload)
        self.assertIn("generated_at", payload)
        self.assertIn("cards", payload)
        self.assertIn("timeline", payload)
        self.assertIn("charts", payload)

        self.assertIn("current_mis", payload["cards"])
        self.assertIn("inbound_move_count", payload["cards"])
        self.assertIn("outbound_move_count", payload["cards"])
        self.assertIn("net_position_value_delta", payload["cards"])

        self.assertGreaterEqual(len(payload["charts"]["mis_trend"]), 1)
        self.assertGreaterEqual(len(payload["charts"]["position_group_delta"]), 1)


if __name__ == "__main__":
    unittest.main()
