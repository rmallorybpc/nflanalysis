# Feature Pipelines

## Team-Week Feature Set (Issue #8)

Build canonical team-week features from processed movement, player, and outcome tables:

```bash
/usr/bin/python3 pipelines/features/build_team_week_features.py \
  --movement data/processed/movement_events.csv \
  --players data/processed/player_dimension.csv \
  --outcomes data/processed/team_week_outcomes.csv \
  --position-weights data/external/position_value_weights.csv \
  --output data/processed/team_week_features.csv \
  --feature-version 0.1.0 \
  --replace
```

Current features:

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

Notes:

- `roster_churn_rate` is normalized by roster baseline (default 53).
- Position weights are configurable via `data/external/position_value_weights.csv`.
- Group deltas sum to `position_value_delta`.
- `schedule_strength_index` is currently a placeholder baseline value and will be replaced in Issue #10.
