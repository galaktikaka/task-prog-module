#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> Поднять PostgreSQL и MySQL"
docker compose up -d --wait

echo "==> Установить зависимости Python (если нужно)"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
# MySQL 8 + PyMySQL требует cryptography для caching_sha2_password
pip install -q cryptography

echo "==> Прогон демонстраций аномалий"
python scripts/run_demos.py

echo ""
echo "Готово. Логи: results/"
echo "Отчёт: REPORT.md"
echo ""
echo "Ручной прогон (два терминала psql):"
echo "  docker exec -it isolation-demo-postgres psql -U demo -d isolation_demo"
echo "  см. sql/02_non_repeatable_read.sql и др."
