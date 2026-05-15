#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

QUICK=false
if [[ "${1:-}" == "--quick" ]]; then
  QUICK=true
fi

echo "==> Starting infrastructure (PostgreSQL, Redis, 3 app instances)"
docker compose down -v 2>/dev/null || true
docker compose up -d --build

echo "==> Waiting for services..."
for port in 8001 8002 8003; do
  for i in $(seq 1 60); do
    if curl -sf "http://localhost:${port}/health" >/dev/null 2>&1; then
      echo "    OK :${port}"
      break
    fi
    if [[ "$i" -eq 60 ]]; then
      echo "Timeout waiting for :${port}"
      docker compose logs
      exit 1
    fi
    sleep 1
  done
done

echo "==> Python venv + dependencies"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

BENCH_ARGS=(--out-dir results)
if $QUICK; then
  BENCH_ARGS+=(--quick)
fi

mkdir -p results
echo "==> Running unified benchmark (9 runs: 3 strategies x 3 profiles)"
python load_generator/benchmark.py "${BENCH_ARGS[@]}" 2>&1 | tee results/console.log

echo "==> Saving Write-Back flush logs (для отчёта / скринов)"
docker compose logs --no-color app-write-back 2>&1 | tail -80 > results/docker_write_back.log || true

echo ""
echo "Done. See REPORT.md, results/benchmark_results.md, results/console.log"
