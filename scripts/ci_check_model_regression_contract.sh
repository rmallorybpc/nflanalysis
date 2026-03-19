#!/usr/bin/env bash
set -euo pipefail

echo "Running model regression contract checks..."

if [[ ! -f docs/modeling-notes.md ]]; then
  echo "Missing docs/modeling-notes.md"
  exit 1
fi

if [[ ! -d models/artifacts ]]; then
  echo "Missing models/artifacts directory"
  exit 1
fi

grep -qi "hierarchical" docs/modeling-notes.md || {
  echo "modeling-notes.md should mention hierarchical modeling plan"
  exit 1
}

echo "Model regression contract checks passed."
