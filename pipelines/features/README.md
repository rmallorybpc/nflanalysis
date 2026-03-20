# Feature Pipelines

## Team-Week Feature Set (Issue #8)

Build canonical team-week features from processed movement, player, and outcome tables:

```bash
/usr/bin/python3 pipelines/features/build_team_week_features.py \
  --movement data/processed/movement_events.csv \
  --players data/processed/player_dimension.csv \
  --outcomes data/processed/team_week_outcomes.csv \
  --output data/processed/team_week_features.csv \
  --feature-version 0.1.0 \
  --replace
```

Current features:

- roster_churn_rate
- inbound_move_count
- outbound_move_count
- position_value_delta
- schedule_strength_index
- feature_version

Notes:

- `roster_churn_rate` is normalized by roster baseline (default 53).
- `position_value_delta` is a weighted net inbound minus outbound signal by player position.
- `schedule_strength_index` is currently a placeholder baseline value and will be replaced in Issue #10.
