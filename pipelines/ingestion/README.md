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
