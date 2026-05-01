# NFL Analysis

## Overview
Front office in a browser. NFL Analysis is a live decision-support system that quantifies how trades and free-agency moves shift team outcomes, combining a production dashboard at [https://rmallorybpc.github.io/nflanalysis/dashboard/src/](https://rmallorybpc.github.io/nflanalysis/dashboard/src/), a REST API for dashboard-grade slices, and a five-season dataset (2022-2026) used for modeling, ranking, and counterfactual analysis across all 32 teams.

## Live Dashboard
- [Overview](https://rmallorybpc.github.io/nflanalysis/dashboard/src/): league-wide movement impact ranking for all 32 teams across five seasons.
- [Team Detail](https://rmallorybpc.github.io/nflanalysis/dashboard/src/team.html): inbound/outbound movement cards, MIS trend, position group delta, and scenario launch for any team.
- [Scenario Sandbox](https://rmallorybpc.github.io/nflanalysis/dashboard/src/scenario.html): counterfactual what-if analysis - add or remove a player move and inspect the modeled outcome delta.

## Data
- Five seasons: 2022, 2023, 2024, 2025, 2026
- 542 movement events (trades and free agency signings)
- 32 teams, three outcome metrics: win%, point differential per game, offensive EPA per play
- Sources: nflverse trades data, 2026 offseason transactions

## Pipeline
Run the full system with:

1. Fetch all seasons:

```bash
bash scripts/fetch_all_seasons.sh
```

2. Run the pipeline:

```bash
bash run_final.sh
```

Pipeline stages:

- Fetch: pull raw seasonal transaction and context inputs.
- Ingest: normalize raw files into canonical movement and dimension tables.
- Feature build: assemble model-ready team and movement feature matrices.
- Model training: fit baseline and hierarchical models and emit scored outputs.

## API
Base URL: [https://nflanalysis.onrender.com](https://nflanalysis.onrender.com)

Confirmed endpoints:

- GET `/v1/dashboard/overview?season={year}`
- GET `/v1/dashboard/team-detail?team_id={id}&season={year}`

## Models
- Baseline: regularized ridge regression, version `baseline-ridge-v0.2.0-offseason`
- Hierarchical: empirical-Bayes with partial pooling, version `hierarchical-eb-v0.2.0-offseason`
- Known limitation: individual player effects require multi-season repeated observations; single-season offseason snapshots produce near-zero player-level effects due to empirical-Bayes shrinkage

## CI
GitHub Actions runs three jobs on every push to `main`: CSV validation, pipeline smoke test, and model regression check.

Local check:

```bash
bash scripts/ci_check_data_quality.sh
```

## Metric Specification

Use this as the first model contract for analytics + product.

### Target Metric

Movement Impact Score (MIS) for team t in period p:

$$
\\text{MIS}_{t,p} = \hat{Y}^{\text{observed}}_{t,p} - \hat{Y}^{\text{counterfactual no-move}}_{t,p}
$$

Where:

- $\hat{Y}$ is predicted team performance under a fixed model
- Performance can be win%, point differential/game, or EPA/play

### Standardization

To compare across outcomes and seasons:

$$
\\text{MIS}^{z}_{t,p} = \frac{\text{MIS}_{t,p} - \mu_{\text{season,outcome}}}{\sigma_{\text{season,outcome}}}
$$

### Portfolio Decomposition

Total team movement impact decomposition:

$$
\\text{MIS}_{t,p}^{\text{total}} = \sum_{i \in \text{incoming}} \text{MIS}_{i,t,p}^{+} + \sum_{j \in \text{outgoing}} \text{MIS}_{j,t,p}^{-} + \epsilon_{t,p}^{\text{interaction}}
$$

### Confidence Reporting

- Display median estimate
- Display 50% and 90% intervals
- Flag "low confidence" when interval width exceeds configurable threshold

### Business Interpretation Bands

- High positive impact: MIS^z >= 1.0
- Moderate positive impact: 0.3 <= MIS^z < 1.0
- Neutral: -0.3 < MIS^z < 0.3
- Moderate negative impact: -1.0 < MIS^z <= -0.3
- High negative impact: MIS^z <= -1.0
