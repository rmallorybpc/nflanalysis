# MVP Metric Specification

This document defines the first production contract for movement impact estimation.

## 1. Purpose

Quantify how player movement events (in-season trades and off-season free agency moves) affect team-level performance outcomes.

## 2. Scope

### Included event types

- In-season trades
- Off-season free agent signings

### Included outcomes

- Team win percentage
- Point differential per game
- Offensive EPA per play

### Granularity

- Team-week (in-season updates)
- Team-season (rollups)

## 3. Core Metric

Movement Impact Score (MIS) for team $t$ in period $p$:

$$
\text{MIS}_{t,p} = \hat{Y}^{\text{observed}}_{t,p} - \hat{Y}^{\text{counterfactual no-move}}_{t,p}
$$

Where:

- $\hat{Y}^{\text{observed}}_{t,p}$ is model-predicted team outcome under observed movement events.
- $\hat{Y}^{\text{counterfactual no-move}}_{t,p}$ is model-predicted team outcome with movement events removed.

Interpretation:

- Positive MIS indicates net favorable impact from movement events.
- Negative MIS indicates net unfavorable impact from movement events.

## 4. Standardized Score

To compare MIS across seasons and outcomes:

$$
\text{MIS}^{z}_{t,p} = \frac{\text{MIS}_{t,p} - \mu_{\text{season,outcome}}}{\sigma_{\text{season,outcome}}}
$$

Where:

- $\mu_{\text{season,outcome}}$ and $\sigma_{\text{season,outcome}}$ are estimated over all teams for a given season and target outcome.

## 5. Team Portfolio Decomposition

Decompose total team effect into inbound, outbound, and interactions:

$$
\text{MIS}_{t,p}^{\text{total}} = \sum_{i \in \text{incoming}} \text{MIS}_{i,t,p}^{+} + \sum_{j \in \text{outgoing}} \text{MIS}_{j,t,p}^{-} + \epsilon_{t,p}^{\text{interaction}}
$$

Notes:

- $\epsilon_{t,p}^{\text{interaction}}$ captures non-additive effects (fit, scheme, depth-chart dependencies).

## 6. Confidence and Reliability

For every displayed estimate, report:

- Median estimate
- 50% interval
- 90% interval

Low-confidence flag condition:

- Mark estimate as low confidence when 90% interval width exceeds threshold $\tau$.

Default threshold recommendation:

- $\tau = 0.75 \cdot \sigma_{\text{season,outcome}}$

## 7. Interpretation Bands

Apply to standardized score $\text{MIS}^z$:

- High positive impact: $\text{MIS}^z \ge 1.0$
- Moderate positive impact: $0.3 \le \text{MIS}^z < 1.0$
- Neutral: $-0.3 < \text{MIS}^z < 0.3$
- Moderate negative impact: $-1.0 < \text{MIS}^z \le -0.3$
- High negative impact: $\text{MIS}^z \le -1.0$

## 8. Identification and Controls

The metric relies on causal framing choices in the model layer. Required controls:

- Opponent and schedule strength
- Injuries and player availability
- Coaching/scheme continuity changes
- Baseline team strength and pre-trend checks

Recommended design for MVP:

- Difference-in-differences event windows around movement events
- Hierarchical partial pooling for player-position-team effects

## 9. API Contract Requirements

Every MIS response object should include:

- `team_id`
- `season`
- `period`
- `outcome_name`
- `mis_value`
- `mis_z`
- `median`
- `interval_50_low`
- `interval_50_high`
- `interval_90_low`
- `interval_90_high`
- `low_confidence_flag`
- `model_version`
- `data_version`
- `run_timestamp`

## 10. Acceptance Criteria

The metric implementation is accepted when:

- Counterfactual generation is deterministic given fixed model and data versions.
- Backtests for the last 5 seasons are reproducible.
- Confidence intervals are returned for 100% of dashboard-exposed estimates.
- Unit and integration tests validate schema, range, and monotonicity constraints where applicable.
