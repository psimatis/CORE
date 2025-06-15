#!/usr/bin/env bash
###############################################################################
# run.sh – Drive CORE's offline engine in Docker and capture a timestamped log
#
# Usage:
#   ./run.sh [QUERY_FILE] [DECLARATION_FILE] [CSV_FILE]
#
# If you omit arguments the Smart‑Homes demo included in the repo is used.
# A log is written to ./logs/ with the query name and a UTC timestamp.
###############################################################################
set -euo pipefail

#------------------------------------------------------------------------
# Resolve repository root (directory containing this script)
#------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#------------------------------------------------------------------------
# Pick arguments or fall back to demo data
#------------------------------------------------------------------------
QUERY="${1:-src/targets/experiments/smart_homes/queries/q1_none.txt}"
DECL="${2:-src/targets/experiments/smart_homes/declaration.core}"
CSV="${3:-src/targets/experiments/smart_homes/smart_homes_data.csv}"

# Basic sanity check
for f in "$QUERY" "$DECL" "$CSV"; do
  if [[ ! -f "$REPO_ROOT/$f" ]]; then
    echo "❌  Can't find $f" >&2
    exit 1
  fi
done

#------------------------------------------------------------------------
# Prepare log file – ./logs/<query>_YYYY-MM-DD_HH-MM-SS.log
#------------------------------------------------------------------------
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +"%Y-%m-%d_%H-%M-%S")"
BASE="$(basename "${QUERY%%.*}")"   # strip extension
LOG_FILE="$LOG_DIR/${BASE}_${STAMP}.log"

echo "▶ Running CORE – log → $LOG_FILE"

#------------------------------------------------------------------------
# Launch the pre‑built engine in the runtime container and tee output
#------------------------------------------------------------------------
docker compose run --rm \
  -e TRACY_NO_INVARIANT_CHECK=1 \
  -v "$REPO_ROOT":/workspace \
  -w /workspace \
  core-terminal \
  /CORE/build/Release/offline \
    --query "$QUERY" \
    --declaration "$DECL" \
    --csv "$CSV" 2>&1 | tee "$LOG_FILE"

exit ${PIPESTATUS[0]}  # propagate offline's exit code
