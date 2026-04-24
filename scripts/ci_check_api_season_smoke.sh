#!/usr/bin/env bash
set -euo pipefail

echo "Running API season smoke checks..."

export OFFSEASON_SERVING_BUNDLE="${OFFSEASON_SERVING_BUNDLE:-data/processed/offseason/backfill_2022_2026}"

python3 - <<'PY'
from api.app.counterfactual_service import CounterfactualService, ServiceConfig

service = CounterfactualService(config=ServiceConfig.from_env())
required = [2022, 2023, 2024, 2025, 2026]

for season in required:
    overview = service.build_overview_payload(season=season)
    if overview["season"] != season:
        raise SystemExit(f"overview season mismatch for {season}")

    rows = [
        row
        for row in service.model_rows
        if int(row["nfl_season"]) == season and row["outcome_name"].strip() == "win_pct"
    ]
    if not rows:
        raise SystemExit(f"missing win_pct rows for season={season}")

    team_id = rows[0]["team_id"].strip()
    week = max(int(row["nfl_week"]) for row in rows if row["team_id"].strip() == team_id)

    detail = service.build_team_detail_payload(team_id=team_id, season=season)
    if detail["team_id"] != team_id or detail["season"] != season:
        raise SystemExit(f"team-detail mismatch for season={season} team={team_id}")

    sandbox = service.build_scenario_sandbox_payload(
        team_id=team_id,
        season=season,
        week=week,
        scenario_id=f"ci-smoke-{season}",
        moves=[],
    )
    if sandbox["season"] != season:
        raise SystemExit(f"scenario-sandbox mismatch for season={season}")

unsupported = min(required) - 1
try:
    service.build_overview_payload(season=unsupported)
except ValueError:
    pass
else:
    raise SystemExit(f"expected unsupported season to fail: season={unsupported}")

print("validated API smoke seasons:", required)
print("validated unsupported season handling:", unsupported)
PY

echo "API season smoke checks passed"
