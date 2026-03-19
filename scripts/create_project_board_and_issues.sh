#!/usr/bin/env bash
set -euo pipefail

# Creates labels, milestones, and the first 20 issues for nflanalysis.
# By default, this script runs in dry-run mode.
# Use --apply to execute against GitHub.

REPO="rmallorybpc/nflanalysis"
APPLY=false

if [[ "${1:-}" == "--apply" ]]; then
  APPLY=true
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install: https://cli.github.com/"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh CLI is not authenticated. Run: gh auth login"
  exit 1
fi

run_cmd() {
  if [[ "$APPLY" == true ]]; then
    echo "+ $*"
    eval "$*"
  else
    echo "DRY RUN: $*"
  fi
}

ensure_label() {
  local name="$1"
  local color="$2"
  local description="$3"

  if gh label list --repo "$REPO" --limit 200 --json name --jq '.[].name' | grep -Fxq "$name"; then
    run_cmd "gh label edit '$name' --repo '$REPO' --color '$color' --description '$description'"
  else
    run_cmd "gh label create '$name' --repo '$REPO' --color '$color' --description '$description'"
  fi
}

ensure_milestone() {
  local title="$1"
  local description="$2"

  if gh api "repos/$REPO/milestones?state=all&per_page=100" --jq ".[] | .title" | grep -Fxq "$title"; then
    echo "Milestone exists: $title"
  else
    run_cmd "gh api repos/$REPO/milestones -X POST -f title='$title' -f description='$description'"
  fi
}

get_milestone_number() {
  local title="$1"
  gh api "repos/$REPO/milestones?state=all&per_page=100" --jq ".[] | select(.title == \"$title\") | .number"
}

create_issue() {
  local title="$1"
  local body="$2"
  local labels="$3"
  local milestone_title="$4"

  if gh issue list --repo "$REPO" --state all --search "\"$title\" in:title" --json title --jq '.[].title' | grep -Fxq "$title"; then
    echo "Issue exists, skipping: $title"
    return 0
  fi

  if [[ "$APPLY" == true ]]; then
    local milestone_number
    milestone_number="$(get_milestone_number "$milestone_title")"

    if [[ -z "$milestone_number" ]]; then
      echo "Missing milestone number for: $milestone_title"
      exit 1
    fi
  fi

  run_cmd "gh issue create --repo '$REPO' --title '$title' --body '$body' --label '$labels' --milestone '$milestone_title'"
}

echo "Preparing labels..."
ensure_label "data-foundation" "0e8a16" "Data sources, ingestion, and quality checks"
ensure_label "feature-engineering" "1d76db" "Feature design and transformation pipelines"
ensure_label "modeling" "5319e7" "Model training, evaluation, and inference"
ensure_label "dashboard" "fbca04" "Frontend analytics dashboard"
ensure_label "validation" "d93f0b" "Backtesting, QA, and regression checks"

echo "Preparing milestones..."
ensure_milestone "Milestone 1: Data Foundation" "Week 1-2"
ensure_milestone "Milestone 2: Feature + Baseline Model" "Week 3-4"
ensure_milestone "Milestone 3: Hierarchical + Counterfactual" "Week 5-6"
ensure_milestone "Milestone 4: Dashboard MVP + Release Hardening" "Week 7-8"

echo "Creating issues..."
create_issue "Define canonical player movement schema (trade + FA)" "Define canonical event schema fields for in-season trades and off-season free agent signings." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Build NFL week/date calendar mapping table" "Create a canonical mapping from dates to NFL season/week, including offseason windows." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Implement movement event ingestion pipeline" "Build ingestion jobs for movement events with idempotent upsert behavior." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Create player metadata normalization job" "Normalize player metadata (position, age, experience, identifiers) across all sources." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Build team-week outcome aggregation table" "Aggregate team-level weekly outcome metrics (win%, point differential/game, offensive EPA/play)." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Add data quality checks for missing key fields" "Implement checks for required fields and temporal consistency in movement and outcome tables." "validation,data-foundation" "Milestone 1: Data Foundation"
create_issue "Document data dictionary for all MVP tables" "Write field-level data dictionary for canonical tables consumed by feature and model pipelines." "data-foundation" "Milestone 1: Data Foundation"
create_issue "Implement roster churn feature set by team-week" "Compute team-week roster churn features from incoming/outgoing movement events." "feature-engineering" "Milestone 2: Feature + Baseline Model"
create_issue "Implement position-group value delta features" "Create inbound/outbound talent deltas by position group and usage-weighted role." "feature-engineering" "Milestone 2: Feature + Baseline Model"
create_issue "Add schedule strength and opponent adjustments" "Add normalized schedule strength controls and opponent-adjusted features." "feature-engineering" "Milestone 2: Feature + Baseline Model"
create_issue "Build baseline regularized regression model" "Implement interpretable baseline model for team outcome deltas." "modeling" "Milestone 2: Feature + Baseline Model"
create_issue "Add time-based backtest split framework" "Create reproducible temporal train/validation/test split logic for historical seasons." "validation,modeling" "Milestone 2: Feature + Baseline Model"
create_issue "Implement pre-trend and placebo validation tests" "Add pre-trend diagnostics and placebo tests for movement impact identification." "validation,modeling" "Milestone 2: Feature + Baseline Model"
create_issue "Build hierarchical player-position-team model" "Train a hierarchical model with partial pooling for sparse players/roles." "modeling" "Milestone 3: Hierarchical + Counterfactual"
create_issue "Implement counterfactual simulation endpoint" "Expose an API endpoint returning no-move counterfactual predictions and deltas." "modeling" "Milestone 3: Hierarchical + Counterfactual"
create_issue "Define API schemas for dashboard cards/charts" "Define typed response schemas for overview cards, timelines, and scenario outputs." "dashboard" "Milestone 4: Dashboard MVP + Release Hardening"
create_issue "Build Overview dashboard page" "Implement league-wide movement impact view with ranking and filters." "dashboard" "Milestone 4: Dashboard MVP + Release Hardening"
create_issue "Build Team detail page with movement timeline" "Implement team page with inbound/outbound cards and pre/post trend charts." "dashboard" "Milestone 4: Dashboard MVP + Release Hardening"
create_issue "Build Scenario sandbox with uncertainty output" "Implement scenario interface to add/remove moves and display interval-based outputs." "dashboard" "Milestone 4: Dashboard MVP + Release Hardening"
create_issue "Add CI workflow for data validation + model regression tests" "Add CI checks for data quality, model regressions, and dashboard schema contract tests." "validation" "Milestone 4: Dashboard MVP + Release Hardening"

echo "Done."
if [[ "$APPLY" == false ]]; then
  echo "Dry run complete. Re-run with --apply to execute."
fi
