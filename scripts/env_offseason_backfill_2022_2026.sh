#!/usr/bin/env bash
set -euo pipefail

# Compatibility shim retained for existing references.
# Prefer sourcing env_offseason_backfill_2017_2026.sh directly.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/env_offseason_backfill_2017_2026.sh"