# Практика: сравнение типов кеширования

Три варианта одной системы (ключ-значение по `item_id`) с разными стратегиями кеша:

| Сервис | Порт | Стратегия |
|--------|------|-----------|
| `app-cache-aside` | 8001 | Cache-Aside / Lazy Loading |
| `app-write-through` | 8002 | Write-Through |
| `app-write-back` | 8003 | Write-Back |

Инфраструктура: **PostgreSQL** (БД), **Redis** (кеш), **FastAPI** (приложение), **load_generator** (единый нагрузочный тест).

## Быстрый старт

```bash
chmod +x run.sh
./run.sh          # полный прогон: 30 с, 200 req/s
./run.sh --quick  # быстрая проверка: 10 с, 100 req/s
```

Результаты: `results/benchmark_results.csv`, `results/benchmark_results.md`, `results/console.log`.

Итоговый отчёт для сдачи: [REPORT.md](REPORT.md).

## Ручной запуск

```bash
docker compose up -d --build
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python load_generator/benchmark.py --duration 30 --rps 200
```

## API

- `GET /items/{id}` — чтение
- `PUT /items/{id}` — запись (`{"value": "..."}`)
- `GET /metrics` — метрики (hit rate, обращения к БД)
- `POST /admin/reset-metrics` — сброс счётчиков перед прогоном
- `POST /admin/flush` — принудительный сброс dirty-записей (Write-Back)

## Единый тест

Для каждой стратегии три профиля нагрузки:

- `read_heavy` — 80% read / 20% write
- `balanced` — 50% / 50%
- `write_heavy` — 20% read / 80% write

Одинаковые: пул ключей (500), длительность, целевой RPS, число воркеров.

## Сдача на Git

```bash
git init
git add .
git commit -m "Практика: сравнение Cache-Aside, Write-Through, Write-Back"
git remote add origin <URL-репозитория>
git push -u origin main
```

## Структура

```
app/                  # приложение и 3 стратегии
load_generator/       # единый бенчмарк
docker/               # init.sql
results/              # артефакты прогонов
REPORT.md             # отчёт с выводами
```
