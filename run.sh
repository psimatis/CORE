# Examples
# ./run.sh            # remote image, Release build (default)
# ./run.sh local      # local image,   Release build
# ./run.sh local debug
# ./run.sh remote debug

set -euo pipefail

# ./run.sh [local|remote] [debug|release]
# - remote  (default): use pre‑built crivero1/cer-core via docker‑compose
# - local            : build (if needed) and run image "core-dev"
#
MODE=${1:-remote}
BUILD=${2:-release}
MODE=${MODE,,}; BUILD=${BUILD,,}

IMG_REMOTE=core-terminal    # service name in docker-compose.yml
IMG_LOCAL=core-dev          # tag for locally‑built image
DIR=$([[ $BUILD == debug ]] && echo Debug || echo Release)

CMD=(/CORE/build/$DIR/offline \
     --query src/targets/experiments/stocks/queries/other-q1_none.txt \
     --declaration src/targets/experiments/stocks/declaration.core \
     --csv src/targets/experiments/stocks/stock_data.csv)

if [[ $MODE == remote ]]; then
  docker compose run --rm -e TRACY_NO_INVARIANT_CHECK=1 $IMG_REMOTE "${CMD[@]}"
else
  # build image once if it doesn't exist
  if ! docker image inspect $IMG_LOCAL > /dev/null 2>&1; then
    echo "Building local image ($IMG_LOCAL)… this can take several minutes."
    docker build --target build -t $IMG_LOCAL .
  fi
  docker run --rm -e TRACY_NO_INVARIANT_CHECK=1 \
    -v "$PWD":/workspace -w /workspace \
    $IMG_LOCAL "${CMD[@]}"
fi
