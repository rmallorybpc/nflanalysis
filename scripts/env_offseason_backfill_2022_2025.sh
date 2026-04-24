#!/usr/bin/env bash
set -euo pipefail

# Compatibility shim for the renamed 2022-2026 backfill profile.
# Prefer sourcing env_offseason_backfill_2022_2026.sh directly.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/env_offseason_backfill_2022_2026.sh"
