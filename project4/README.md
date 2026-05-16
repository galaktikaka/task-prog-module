# Практика: аномалии изоляции в SQL

Демонстрация четырёх аномалий параллельных транзакций:

| Аномалия | СУБД | Уровень изоляции |
|----------|------|------------------|
| Dirty read | MySQL 8 | `READ UNCOMMITTED` |
| Non-repeatable read | PostgreSQL 16 | `READ COMMITTED` |
| Phantom read | PostgreSQL 16 | `READ COMMITTED` |
| Lost update | PostgreSQL 16 | `READ COMMITTED` |

> **Почему два сервера?** В PostgreSQL уровень `READ UNCOMMITTED` работает как `READ COMMITTED`, поэтому «грязное чтение» там **не воспроизводится**. Для dirty read используется MySQL; остальные три сценария — PostgreSQL.

## Быстрый старт

```bash
chmod +x run.sh
./run.sh
```

Скрипт поднимает Docker (`postgres` на порту **5434**, `mysql` на **3307**), запускает `scripts/run_demos.py` и пишет логи в `results/`.

## Структура

```
project4/
  docker-compose.yml      # PostgreSQL + MySQL
  docker/init.sql           # схема PG
  docker/init-mysql.sql     # схема MySQL
  sql/                      # пошаговые сценарии для ручного прогона
  scripts/run_demos.py      # автоматический прогон
  results/                  # логи (после ./run.sh)
  screenshots/              # скриншоты для REPORT.md
  REPORT.md                 # отчёт для сдачи
```

## Ручной прогон (два терминала)

PostgreSQL:

```bash
docker exec -it isolation-demo-postgres psql -U demo -d isolation_demo
```

MySQL (dirty read):

```bash
docker exec -it isolation-demo-mysql mysql -u demo -pdemo isolation_demo
```

Шаги — в файлах `sql/01_dirty_read_mysql.sql` … `sql/04_lost_update.sql`.

## Сброс данных

```bash
docker exec -i isolation-demo-postgres psql -U demo -d isolation_demo < sql/00_reset.sql
```
