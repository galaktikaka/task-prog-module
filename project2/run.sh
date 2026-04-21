#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

docker compose up -d rabbitmq redis

echo "Waiting for RabbitMQ to be ready..."
for _ in {1..30}; do
  if docker exec bench-rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec bench-rabbitmq rabbitmq-diagnostics -q ping >/dev/null

echo "Waiting for Redis to be ready..."
for _ in {1..30}; do
  if docker exec bench-redis redis-cli ping >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec bench-redis redis-cli ping >/dev/null

python src/benchmark.py \
  --brokers rabbitmq,redis \
  --sizes 128,1024,10240,102400 \
  --rates 1000,5000,10000 \
  --duration 30 \
  --producers 2 \
  --consumers 2 \
  --drain-timeout 5 \
  --out-dir results
