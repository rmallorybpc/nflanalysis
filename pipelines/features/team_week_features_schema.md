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
- offense_skill_value_delta
- offense_line_value_delta
- defense_front_value_delta
- defense_second_level_value_delta
- defense_secondary_value_delta
- special_teams_value_delta
- other_value_delta
- position_value_delta
- schedule_strength_index
- feature_version
- generated_at

Behavior:

- Feature rows are generated for each key present in team_week_outcomes.
- Upsert behavior is keyed by (team_id, nfl_season, nfl_week).
- Position-group deltas are weighted net inbound minus outbound movement per group.
- schedule_strength_index is computed from prior-week opponent win rates and normalized around 0.5.
- `--replace` rebuilds output from current inputs.
