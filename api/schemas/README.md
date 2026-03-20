# API Schema Catalog

This folder contains JSON Schemas for dashboard-facing API payload contracts.

## Available Schemas

- movement-impact.schema.json
  - Canonical team impact + scenario output payload used by the simulation endpoint.
- overview-dashboard.schema.json
  - Overview page cards and ranking/distribution chart payload.
- team-detail.schema.json
  - Team page cards, movement timeline, MIS trend chart, and position group deltas.
- scenario-sandbox.schema.json
  - Scenario sandbox payload comparing baseline and scenario estimates, including deltas.

## Notes

- Schemas use JSON Schema Draft 2020-12.
- Outcome names are constrained to MVP outcomes:
  - win_pct
  - point_diff_per_game
  - offensive_epa_per_play
