# Отчёт: сравнение типов кеширования

## 1. Цель

Сравнить три стратегии кеширования на **одной и той же системе** в одинаковых условиях:

| № | Стратегия | Поведение |
|---|-----------|-----------|
| 1 | **Cache-Aside** (Lazy Loading / Write-Around) | Чтение через кеш; при промахе — БД → кеш. Запись сразу в БД, кеш инвалидируется. |
| 2 | **Write-Through** | Чтение через кеш. Запись одновременно в кеш и БД. |
| 3 | **Write-Back** | Чтение через кеш. Запись сначала в кеш (dirty), в БД — пакетами по таймеру. |

---

## 2. Архитектура

```
load_generator  →  FastAPI (3 инстанса)  →  Redis (кеш)  →  PostgreSQL (БД)
                      :8001 cache_aside
                      :8002 write_through
                      :8003 write_back
```

- **БД:** PostgreSQL 16, таблица `items`, 500 предзагруженных ключей (`docker/init.sql`).
- **Кеш:** Redis 7, отдельная logical DB на стратегию (0/1/2).
- **Приложение:** Python 3.12, FastAPI, `asyncpg`, `redis`.
- **Нагрузка:** `load_generator/benchmark.py` — единый скрипт для всех трёх вариантов.

Запуск: `./run.sh` (или уже поднятый `docker compose up -d` + `python load_generator/benchmark.py`).

---

## 3. Единый тест

| Параметр | Значение |
|----------|----------|
| Длительность одного прогона | **30 с** |
| Целевой RPS | **200** |
| Воркеры | **8** |
| Пул ключей | **500** (id 1…500) |
| Ошибки | **0** во всех прогонах |

**Профили нагрузки:**

| Профиль | Read | Write |
|---------|------|-------|
| `read_heavy` | 80% | 20% |
| `balanced` | 50% | 50% |
| `write_heavy` | 20% | 80% |

Перед каждым прогоном: `POST /admin/reset-metrics`. Для Write-Back после прогона — ожидание flush и `POST /admin/flush`.

---

## 4. Метрики

| Метрика | Как измеряется |
|---------|----------------|
| **Throughput (req/s)** | `total_requests / duration_s` в load generator |
| **Средняя задержка** | среднее время HTTP-запроса (ms) |
| **P95 задержка** | 95-й перцентиль (ms) |
| **Обращения к БД** | счётчики `db_reads` + `db_writes` в `/metrics` |
| **Hit rate кеша** | `cache_hits / (hits + misses) * 100%` |
| **Write-Back flush** | `write_back_flushes`, `write_back_flushed_items` |

Артефакты: `results/benchmark_results.csv`, `results/console.log`, `results/docker_write_back.log`.

---

## 5. Таблица результатов

### 5.1. Сводная

| Стратегия | Профиль | Throughput (req/s) | Avg latency (ms) | P95 (ms) | DB reads | DB writes | DB total | Hit rate % | WB flushes | WB flushed |
|-----------|---------|-------------------:|-----------------:|---------:|---------:|----------:|---------:|-----------:|-----------:|-----------:|
| cache_aside | read_heavy | 1228.5 | 6.50 | 18.53 | 6135 | 7365 | **13500** | 79.2 | — | — |
| cache_aside | balanced | 1204.0 | 6.64 | 18.04 | 8901 | 18092 | **26993** | 50.6 | — | — |
| cache_aside | write_heavy | 1214.9 | 6.58 | 16.68 | 5827 | 29143 | **34970** | 20.2 | — | — |
| write_through | read_heavy | 1201.5 | 6.65 | 19.00 | 0 | 7258 | **7258** | 100.0 | — | — |
| write_through | balanced | 1160.3 | 6.89 | 18.24 | 0 | 17324 | **17324** | 100.0 | — | — |
| write_through | write_heavy | 1122.1 | 7.13 | 17.79 | 0 | 26917 | **26917** | 100.0 | — | — |
| write_back | read_heavy | 1210.5 | 6.60 | 19.92 | 265 | 850 | **1115** | 99.1 | 17 | 850 |
| write_back | balanced | 1151.4 | 6.94 | 20.42 | 0 | 900 | **900** | 100.0 | 18 | 900 |
| write_back | write_heavy | 1074.6 | 7.43 | 22.60 | 0 | 950 | **950** | 100.0 | 19 | 950 |

### 5.2. Write-Back: накопление записей

При **write_heavy** за 30 с отправлено **~25 885 записей** (PUT), а в БД ушло только **950** (19 пакетных flush по ~50 записей).

**Вывод:** Write-Back сильно снижает нагрузку на БД при интенсивной записи, но данные в PostgreSQL отстают от кеша до следующего flush (интервал **2 с**, batch **50**).

---

## 6. Логи

Скриншоты можно сделать из файлов `results/console.log` и `results/docker_write_back.log`.

### 6.1. Вывод бенчмарка (`results/console.log`)

```
>>> cache_aside / read_heavy (read=80%)
[cache_aside   ] profile=read_heavy   req=36855 thr= 1228.5 rps avg=  6.50ms p95= 18.53ms db=13500 hit= 79.2% errors=0

>>> write_through / write_heavy (read=20%)
[write_through ] profile=write_heavy  req=33663 thr= 1122.1 rps avg=  7.13ms p95= 17.79ms db=26917 hit=100.0% errors=0

>>> write_back / write_heavy (read=20%)
[write_back    ] profile=write_heavy  req=32239 thr= 1074.6 rps avg=  7.43ms p95= 22.60ms db=  950 hit=100.0% errors=0
    write-back: flushes=19 flushed_items=950
```

### 6.2. Фоновый flush Write-Back (`results/docker_write_back.log`)

В логах контейнера `app-write-back` видны периодические сбросы dirty-записей в БД:

```
2026-05-15 12:26:15 [INFO] strategies.write_back: Write-Back flush: 50 items -> DB
2026-05-15 12:26:15 [INFO] strategies.write_back: Background flush interval=2.0s flushed=50
2026-05-15 12:26:17 [INFO] strategies.write_back: Write-Back flush: 50 items -> DB
```

Полный лог: `results/docker_write_back.log` (можно приложить скрин этого файла в отчёт).

---

## 7. Выводы

### 7.1. Для чтения (read_heavy, 80% read)

| Критерий | Лучший вариант | Почему |
|----------|----------------|--------|
| Throughput | **Cache-Aside** (~1229 req/s) | Максимальный поток при чтении |
| Задержка | **Cache-Aside** (avg 6.50 ms) | Немного быстрее остальных |
| Нагрузка на БД | **Write-Back** (1115 ops) | Почти все чтения из Redis |
| Hit rate | **Write-Through / Write-Back** (99–100%) | Кеш всегда прогрет после записей |

**Итог:** для чистого чтения оптимален **Cache-Aside** или **Write-Through** с высоким hit rate; **Write-Back** даёт минимум обращений к БД.

### 7.2. Для записи (write_heavy, 80% write)

| Критерий | Лучший вариант | Почему |
|----------|----------------|--------|
| Нагрузка на БД | **Write-Back** (950 ops vs 34970 у Cache-Aside) | Записи буферизуются в Redis |
| Throughput | **Cache-Aside** (~1215 req/s) | Нет синхронной двойной записи |
| Консистентность | **Write-Through** | БД и кеш всегда согласованы |
| Hit rate | **Write-Through / Write-Back** (100%) | После записи данные в кеше |

**Итог:** для интенсивной записи **Write-Back** радикально разгружает БД; **Write-Through** — компромисс «скорость + консистентность»; **Cache-Aside** создаёт максимум операций с БД при write-heavy.

### 7.3. Для смешанной нагрузки (balanced, 50/50)

| Критерий | Лучший вариант |
|----------|----------------|
| Баланс скорости и БД | **Write-Back** (900 DB ops, hit 100%) |
| Простота и предсказуемость | **Write-Through** |
| Универсальность без сложного flush | **Cache-Aside** (но 26993 DB ops) |

**Итог:** при смешанной нагрузке лучший компромисс — **Write-Back** (мало БД, высокий hit rate) или **Write-Through** (если важна немедленная запись в БД).

---


## 9. Как повторить прогон

```bash
chmod +x run.sh
./run.sh              # полный: docker + 30s + 200 rps
./run.sh --quick      # быстрая проверка: 10s + 100 rps
```

Результаты обновятся в `results/`.
