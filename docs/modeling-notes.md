# Modeling Notes

Working notes for model design decisions, experiments, and calibration updates.

## Initial MVP Modeling Plan

- Baseline: regularized regression on team outcome deltas.
- Main: hierarchical player-position-team model with partial pooling.
- Counterfactual: no-move simulation service for scenario evaluation.

## To Fill During Implementation

- Feature importance and stability notes
- Backtest diagnostics by season
- Calibration findings and threshold tuning
- Known failure modes and mitigations

## Geography Robustness Policy (May 2026)

- Overview payload now publishes geography sensitivity views: all events, known-scope-only, and trades-only.
- Strong geography claims are gated by policy checks instead of raw rank alone.
- Current policy thresholds:
	- minimum move count for top and runner-up scopes: 10
	- maximum unknown-scope share: 0.20
	- maximum placebo win_pct one-sided p-value: 0.10
- Payload includes `validation_diagnostics` and `geography_claim_policy` so UI can label exploratory results explicitly.
