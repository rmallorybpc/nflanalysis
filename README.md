# NFL Analysis

Unified modeling and dashboard project to quantify how player movement across teams, divisions, and conferences impacts team performance for:

- In-season moves (trades)
- Off-season moves (free agency)

## 1) Product Goal

Build a decision-ready analytics dashboard that answers:

- Which roster moves changed expected team outcomes the most?
- How much of team performance change is attributable to incoming/outgoing players?
- Do cross-division and cross-conference moves have systematically different impact profiles?

## 2) MVP Scope (6-8 Weeks)

### Included

- Seasons: last 5 completed NFL seasons
- Move types: in-season trades, off-season free agent signings
- Outcomes:
	- Team win percentage
	- Point differential per game
	- Offensive EPA per play
- Geography dimensions:
	- Team, division, conference
- Outputs:
	- Team impact scorecards
	- Movement timeline
	- Scenario simulation card
	- Uncertainty intervals for all impact estimates

### Deferred (Post-MVP)

- Draft pick value propagation
- Contract value efficiency overlays
- Injury shock decomposition
- Playoff probability calibration model

## 3) Repository Structure

Proposed monorepo layout:

```text
nflanalysis/
	README.md
	docs/
		metric-spec.md
		modeling-notes.md
		data-dictionary.md
		adr/
	data/
		raw/
		external/
		processed/
	pipelines/
		ingestion/
		features/
		validation/
	models/
		baseline/
		hierarchical/
		simulation/
		artifacts/
	api/
		app/
		schemas/
		tests/
	dashboard/
		src/
		public/
		tests/
	.github/
		ISSUE_TEMPLATE/
		PULL_REQUEST_TEMPLATE.md
		workflows/
```

## 4) Data Required

### Core Event Data

- Player movement events
	- trade date, effective week/date
	- signing date, contract start
	- source team, destination team
- Player context
	- position, age, experience
	- snap share, usage role
	- injury availability signal

### Team + Game Context

- Weekly team performance metrics (offense/defense/special teams)
- Opponent strength and schedule features
- Coaching/scheme continuity flags
- Division/conference indicators

### Data Quality Rules

- Every movement event must have both source and destination entity
- Event dates must align to NFL week calendar mapping
- Missingness checks on key model features must be tracked by run

## 5) Modeling Approach

### Primary Objective

Estimate marginal team performance impact of player movement, not just correlation.

### MVP Model Stack

1. Baseline interpretable model
	 - Regularized regression on team outcome deltas
2. Hierarchical impact model
	 - Player-position-team random effects
	 - Partial pooling to stabilize sparse players/roles
3. Counterfactual simulation layer
	 - Compute no-move vs observed-move team outcomes

### Identification Strategy

- Difference-in-differences framing around event windows
- Pre-trend checks prior to movement event
- Controls for schedule difficulty, injuries, and coaching changes

### Uncertainty

- Report 50% and 90% intervals on impact estimates
- Flag low-confidence estimates in UI

## 6) Dashboard Requirements

### Live Pages

Main branch live pages:

- [Overview](https://rmallorybpc.github.io/nflanalysis/dashboard/src/)
- [Team Detail](https://rmallorybpc.github.io/nflanalysis/dashboard/src/team.html)
- [Scenario Sandbox](https://rmallorybpc.github.io/nflanalysis/dashboard/src/scenario.html)

### Core Pages

- Overview
	- league-wide movement impact ranking
- Team page
	- inbound/outbound movement cards
	- pre/post trend charts
- Player movement explorer
	- filter by season, position, team, division, conference
- Scenario sandbox
	- remove/add move and recompute expected team delta

### UX Guardrails

- Always show uncertainty next to point estimate
- Distinguish observed outcome from modeled counterfactual
- Avoid causal overclaim language on low-confidence cases

## 7) Milestones

### Milestone 1: Data Foundation (Week 1-2)

- Build event schema and ingestion jobs
- Create canonical movement table
- Publish data dictionary and quality checks

### Milestone 2: Feature + Baseline Model (Week 3-4)

- Implement feature pipeline and baseline model
- Backtest on historical seasons
- Define baseline dashboard API payloads

### Milestone 3: Hierarchical + Counterfactual (Week 5-6)

- Train hierarchical model
- Add simulation service
- Compare baseline vs hierarchical calibration

### Milestone 4: Dashboard MVP + Release Hardening (Week 7-8)

- Implement dashboard pages and filters
- Add model cards + assumptions panel
- Validate end-to-end reproducibility and CI

## 8) First 20 GitHub Issues

Copy this directly into your issue backlog.

1. Define canonical player movement schema (trade + FA)
2. Build NFL week/date calendar mapping table
3. Implement movement event ingestion pipeline
4. Create player metadata normalization job
5. Build team-week outcome aggregation table
6. Add data quality checks for missing key fields
7. Document data dictionary for all MVP tables
8. Implement roster churn feature set by team-week
9. Implement position-group value delta features
10. Add schedule strength and opponent adjustments
11. Build baseline regularized regression model
12. Add time-based backtest split framework
13. Implement pre-trend and placebo validation tests
14. Build hierarchical player-position-team model
15. Implement counterfactual simulation endpoint
16. Define API schemas for dashboard cards/charts
17. Build Overview dashboard page
18. Build Team detail page with movement timeline
19. Build Scenario sandbox with uncertainty output
20. Add CI workflow for data validation + model regression tests

## 9) MVP Metric Specification

Use this as the first model contract for analytics + product.

### Target Metric

Movement Impact Score (MIS) for team t in period p:

$$
\text{MIS}_{t,p} = \hat{Y}^{\text{observed}}_{t,p} - \hat{Y}^{\text{counterfactual no-move}}_{t,p}
$$

Where:

- $\hat{Y}$ is predicted team performance under a fixed model
- Performance can be win%, point differential/game, or EPA/play

### Standardization

To compare across outcomes and seasons:

$$
\text{MIS}^{z}_{t,p} = \frac{\text{MIS}_{t,p} - \mu_{\text{season,outcome}}}{\sigma_{\text{season,outcome}}}
$$

### Portfolio Decomposition

Total team movement impact decomposition:

$$
\text{MIS}_{t,p}^{\text{total}} = \sum_{i \in \text{incoming}} \text{MIS}_{i,t,p}^{+} + \sum_{j \in \text{outgoing}} \text{MIS}_{j,t,p}^{-} + \epsilon_{t,p}^{\text{interaction}}
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

## 10) Definition of Done (MVP)

## 11) 2026 Offseason One-Time Run

For the single-season offseason snapshot workflow, use the dedicated pipeline:

1. Place raw inputs under `data/raw/offseason/`:
	 - `transactions_raw.csv`
	 - `players_metadata.csv`
	 - `team_spending_otc.csv`
	 - `win_totals.csv`
2. Build canonical tables:

```bash
/usr/bin/python3 pipelines/offseason/ingest_offseason_snapshot.py \
	--transactions data/raw/offseason/transactions_raw.csv \
	--players data/raw/offseason/players_metadata.csv \
	--win-totals data/raw/offseason/win_totals.csv \
	--season 2026 \
	--week 1
```

3. Build features (including spending and win totals integration):

```bash
/usr/bin/python3 pipelines/offseason/build_offseason_team_features.py \
	--movement data/processed/movement_events.csv \
	--players data/processed/player_dimension.csv \
	--outcomes data/processed/team_week_outcomes.csv \
	--team-spending data/raw/offseason/team_spending_otc.csv \
	--win-totals data/raw/offseason/win_totals.csv \
	--output data/processed/team_week_features.csv
```

4. Train baseline + hierarchical models locally (no deployment):

```bash
/usr/bin/python3 models/baseline/train_baseline_model.py \
	--features data/processed/team_week_features.csv \
	--outcomes data/processed/team_week_outcomes.csv \
	--output data/processed/model_outputs.csv \
	--coefficients-output models/artifacts/baseline_coefficients.csv \
	--model-version baseline-ridge-v0.2.0-offseason
```

```bash
/usr/bin/python3 models/hierarchical/train_hierarchical_model.py \
	--features data/processed/team_week_features.csv \
	--outcomes data/processed/team_week_outcomes.csv \
	--movement data/processed/movement_events.csv \
	--players data/processed/player_dimension.csv \
	--output data/processed/model_outputs_hierarchical.csv \
	--effects-output models/artifacts/hierarchical_effects.csv \
	--model-version hierarchical-eb-v0.2.0-offseason
```

See `pipelines/offseason/README.md` for details.

The MVP is complete when all conditions are met:

- Data pipelines run end-to-end for last 5 seasons
- Baseline and hierarchical models are trained and versioned
- Counterfactual endpoint returns scenario deltas with intervals
- Dashboard exposes required filters and core pages
- CI validates data quality checks and model regression checks
- Model assumptions and caveats are documented in docs/

## 11) Immediate Next Actions

1. Create milestone labels and project board columns:
	 - data-foundation, feature-engineering, modeling, dashboard, validation
2. Open the first 20 issues and assign milestone + owner
3. Start Milestone 1 by implementing canonical schema + ingestion
