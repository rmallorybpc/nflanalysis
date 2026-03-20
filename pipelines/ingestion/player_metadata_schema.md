# player_metadata source schema

Raw source file: data/raw/player_metadata_source.csv

Required columns:

- player_id
- full_name
- position
- birth_date (YYYY-MM-DD)
- rookie_year (integer)

Optional columns:

- active_status (defaults to active)
- source (defaults to manual_seed)

Normalization behavior:

- Output table upserts by player_id.
- Position is normalized to uppercase and mapped into position_group.
- experience_years is computed from as-of year and rookie_year.
