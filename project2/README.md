# Практика: сравнение RabbitMQ и Redis

Этот проект запускает одинаковые тесты для `RabbitMQ` и `Redis` и сохраняет результаты в `results/`.

## Что реализовано

- единый producer (один формат сообщения JSON);
- единый consumer (одинаковый подсчет сообщений и latency);
- одинаковые параметры для обоих брокеров:
  - размеры сообщения: `128B, 1KB, 10KB, 100KB`;
  - интенсивность: `1000, 5000, 10000 msg/s`;
  - длительность теста;
  - число producers/consumers.
- автоматическая фиксация:
  - sent / received / lost / errors;
  - throughput (messages/sec);
  - avg latency, p95, max;
  - backlog в конце прогона;
  - флаг деградации (`degraded`).

## Быстрый старт

1. Установить Docker и Python 3.10+.
2. В корне проекта:

```bash
chmod +x run.sh
./run.sh
```

После выполнения появятся:

- `results/benchmark_results.csv`
- `results/benchmark_results.md`

## Ручной запуск

```bash
docker compose up -d rabbitmq redis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/benchmark.py --duration 30 --producers 2 --consumers 2 --out-dir results
```

### Быстрая проверка (чтобы не ждать долго)

```bash
python src/benchmark.py --quick --out-dir results_quick
```

`--quick` запускает укороченный набор:
- размеры: `128B`, `1KB`;
- интенсивность: `1000`, `5000 msg/s`;
- длительность: `10s`.

## Интерпретация деградации

Стенд помечает прогон как `degraded=true`, если выполнено хотя бы одно условие:

- backlog в конце прогона > `2 * rate`;
- p95 latency > `200 ms`;
- есть ошибки отправки;
- доставлено < `98%` от отправленных.

Эти пороги можно изменить в `src/benchmark.py`.