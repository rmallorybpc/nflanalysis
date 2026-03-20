# team_week_features output schema

Output file: data/processed/team_week_features.csv

Primary key:

- team_id
- nfl_season
- nfl_week

Fields:

- roster_churn_rate
- inbound_move_count
- outbound_move_count
- position_value_delta
- schedule_strength_index
- feature_version
- generated_at

Behavior:

- Feature rows are generated for each key present in team_week_outcomes.
- Upsert behavior is keyed by (team_id, nfl_season, nfl_week).
- `--replace` rebuilds output from current inputs.
