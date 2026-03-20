# team_game_stats source schema

Raw source file: data/raw/team_game_stats_source.csv

Required columns:

- game_id
- game_date (YYYY-MM-DD)
- team_id
- opponent_team_id
- points_for (integer)
- points_against (integer)
- offensive_epa_per_play (numeric)

Optional columns:

- source

Aggregation behavior:

- Canonical output groups by (team_id, nfl_season, nfl_week).
- Only regular-season rows are aggregated.
- win_pct = (wins + 0.5 * ties) / games_played.
- point_diff_per_game and offensive_epa_per_play are per-week means.
