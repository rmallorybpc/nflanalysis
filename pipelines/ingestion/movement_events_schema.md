# movement_events source schema

Raw source file: data/raw/movement_events_source.csv

Required columns:

- move_id
- event_date (YYYY-MM-DD)
- move_type (trade | free_agency)
- player_id
- from_team_id
- to_team_id

Optional columns:

- effective_date (YYYY-MM-DD, defaults to event_date)
- transaction_detail
- source

Idempotent behavior:

- Output table upserts by move_id.
- Re-running with the same move_id updates the record in place.
