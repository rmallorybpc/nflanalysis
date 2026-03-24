# API

## Issue #15: Counterfactual Simulation Endpoint

Run the local HTTP service:

```bash
/usr/bin/python3 -m api.app.main --host 0.0.0.0 --port 8080
```

Environment variables:

- `ALLOWED_ORIGIN`: comma-separated list of allowed CORS origins.
  - Example: `https://rmallorybpc.github.io`

Health check:

```bash
curl -s http://localhost:8080/health
```

Scenario simulation request:

```bash
curl -s -X POST http://localhost:8080/v1/counterfactual/simulate \
  -H 'Content-Type: application/json' \
  -d '{
    "team_id": "BUF",
    "season": 2024,
    "week": 6,
    "scenario_id": "what-if-add-p001",
    "applied_moves": [
      {
        "move_id": "custom_001",
        "player_id": "p_001",
        "from_team_id": "NYJ",
        "to_team_id": "BUF",
        "move_type": "trade",
        "action": "add"
      }
    ]
  }'
```

Response contract:

- Top-level keys: `team_impact`, `scenario_output`
- Includes estimate-level uncertainty (`interval_50`, `interval_90`) and confidence flags.

Overview dashboard payload:

```bash
curl -s "http://localhost:8080/v1/dashboard/overview?season=2024"
```

Team detail payload:

```bash
curl -s "http://localhost:8080/v1/dashboard/team-detail?team_id=BUF&season=2024"
```

Scenario sandbox payload:

```bash
curl -s -X POST http://localhost:8080/v1/dashboard/scenario-sandbox \
  -H 'Content-Type: application/json' \
  -d '{
    "team_id": "BUF",
    "season": 2024,
    "week": 6,
    "scenario_id": "sandbox-demo",
    "applied_moves": [
      {
        "move_id": "custom_002",
        "player_id": "p_003",
        "from_team_id": "NYJ",
        "to_team_id": "BUF",
        "move_type": "trade",
        "action": "add"
      }
    ]
  }'
```
