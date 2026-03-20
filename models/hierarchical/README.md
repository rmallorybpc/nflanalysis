# Hierarchical Model

## Issue #14: Player-Position-Team Hierarchical Model

Train hierarchical model with partial pooling random effects:

```bash
/usr/bin/python3 models/hierarchical/train_hierarchical_model.py \
  --features data/processed/team_week_features.csv \
  --outcomes data/processed/team_week_outcomes.csv \
  --movement data/processed/movement_events.csv \
  --players data/processed/player_dimension.csv \
  --output data/processed/model_outputs_hierarchical.csv \
  --effects-output models/artifacts/hierarchical_effects.csv \
  --model-version hierarchical-eb-v0.1.0 \
  --alpha 1.0 \
  --prior-strength 3.0
```

Outputs:

- data/processed/model_outputs_hierarchical.csv
- models/artifacts/hierarchical_effects.csv

Approach:

- Fixed effects: baseline ridge regression over canonical team-week features.
- Random effects: movement-linked empirical-Bayes shrinkage for:
  - player-level effects
  - position-group x team effects
- Counterfactual predictions remove movement-driven fixed features and random effects.
