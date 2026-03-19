# Ingestion Pipelines

## NFL Calendar Mapping Table

Build the canonical date-to-season/week mapping table:

```bash
/usr/bin/python3 pipelines/ingestion/build_nfl_calendar_mapping.py \
  --start-season 2018 \
  --end-season 2030 \
  --output data/external/nfl_calendar_mapping.csv
```

Output columns:

- calendar_date
- nfl_season
- season_phase
- phase_week
- nfl_week

Notes:

- This mapping uses deterministic season boundary logic based on a kickoff anchor.
- The output is intended for joins in movement event ingestion and team-week feature pipelines.

## Movement Event Ingestion

Ingest raw movement events and upsert into canonical table:

```bash
/usr/bin/python3 pipelines/ingestion/ingest_movement_events.py \
  --source data/raw/movement_events_source.csv \
  --calendar data/external/nfl_calendar_mapping.csv \
  --output data/processed/movement_events.csv
```

Rebuild output from source (replace mode):

```bash
/usr/bin/python3 pipelines/ingestion/ingest_movement_events.py \
  --source data/raw/movement_events_source.csv \
  --calendar data/external/nfl_calendar_mapping.csv \
  --output data/processed/movement_events.csv \
  --replace
```

Canonical output columns:

- move_id
- event_date
- effective_date
- move_type
- player_id
- from_team_id
- to_team_id
- transaction_detail
- source
- nfl_season
- season_phase
- phase_week
- nfl_week
- ingested_at

## Player Metadata Normalization

Normalize raw player metadata into canonical player dimension table:

```bash
/usr/bin/python3 pipelines/ingestion/normalize_player_metadata.py \
  --source data/raw/player_metadata_source.csv \
  --output data/processed/player_dimension.csv
```

Rebuild output from source (replace mode):

```bash
/usr/bin/python3 pipelines/ingestion/normalize_player_metadata.py \
  --source data/raw/player_metadata_source.csv \
  --output data/processed/player_dimension.csv \
  --replace
```

Canonical output columns:

- player_id
- full_name
- position_group
- position
- birth_date
- rookie_year
- experience_years
- active_status
- source
- normalized_at
