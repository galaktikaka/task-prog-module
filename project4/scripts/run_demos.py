#!/usr/bin/env python3
"""Автоматическое воспроизведение аномалий изоляции и запись логов в results/."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import pymysql

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

PG_DSN = "postgresql://demo:demo@localhost:5434/isolation_demo"
MYSQL = dict(
    host="127.0.0.1",
    port=3307,
    user="demo",
    password="demo",
    database="isolation_demo",
    autocommit=False,
)


def log(lines: list[str], title: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.insert(0, f"=== {title} ===")
    lines.insert(1, f"timestamp: {stamp}")
    lines.append("")


async def reset_postgres(conn: asyncpg.Connection) -> None:
    sql = (ROOT / "sql" / "00_reset.sql").read_text(encoding="utf-8")
    await conn.execute(sql)


def reset_mysql() -> None:
    """Сброс MySQL и снятие зависших транзакций от прошлых прогонов."""
    conn = pymysql.connect(**MYSQL)
    try:
        conn.autocommit(True)
        cur = conn.cursor()
        cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cur.execute("UPDATE accounts SET balance = 1000.00 WHERE id = 1")
    finally:
        conn.close()


async def demo_dirty_read() -> list[str]:
    lines: list[str] = []
    lines.append("СУБД: MySQL 8, isolation READ UNCOMMITTED")
    lines.append("Сценарий: T1 обновляет balance без COMMIT, T2 читает «грязные» данные.")
    lines.append("Примечание: T2 читает без START TRANSACTION — иначе InnoDB ждёт блокировку строки.")

    reset_mysql()

    conn1 = pymysql.connect(**MYSQL)
    conn2 = pymysql.connect(**MYSQL)
    try:
        cur1, cur2 = conn1.cursor(), conn2.cursor()

        # T1: незакоммиченный UPDATE
        conn1.autocommit(False)
        cur1.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur1.execute("UPDATE accounts SET balance = 2500.00 WHERE id = 1")
        cur1.execute("SELECT balance FROM accounts WHERE id = 1")
        t1_balance = cur1.fetchone()[0]
        lines.append(f"T1 после UPDATE (без COMMIT): balance = {t1_balance}")

        # T2: READ UNCOMMITTED + autocommit, без явной транзакции (иначе lock wait timeout)
        conn2.autocommit(True)
        cur2.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur2.execute("SELECT balance FROM accounts WHERE id = 1")
        t2_balance = cur2.fetchone()[0]
        lines.append(f"T2 SELECT (пока T1 не закоммитила): balance = {t2_balance}")
        lines.append(
            f"Dirty read: {'ДА' if float(t2_balance) == 2500.0 else 'НЕТ'} "
            f"(T2 увидела незакоммиченное значение T1)"
        )

        conn1.rollback()
        lines.append("T1: ROLLBACK")

        cur2.execute("SELECT balance FROM accounts WHERE id = 1")
        after_rollback = cur2.fetchone()[0]
        lines.append(f"T2 SELECT после ROLLBACK T1: balance = {after_rollback}")
    finally:
        conn1.close()
        conn2.close()

    return lines


async def demo_non_repeatable_read() -> list[str]:
    lines: list[str] = []
    lines.append("СУБД: PostgreSQL 16, isolation READ COMMITTED (default)")
    lines.append("Сценарий: два SELECT одной строки в одной транзакции, между ними UPDATE+COMMIT в T2.")

    conn1 = await asyncpg.connect(PG_DSN)
    conn2 = await asyncpg.connect(PG_DSN)
    try:
        await reset_postgres(conn1)
        tr1 = conn1.transaction()
        tr2 = conn2.transaction()
        await tr1.start()
        first = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1")
        lines.append(f"T1 первый SELECT: balance = {first}")

        await tr2.start()
        await conn2.execute("UPDATE accounts SET balance = 1500.00 WHERE id = 1")
        await tr2.commit()
        lines.append("T2: UPDATE balance=1500 + COMMIT")

        second = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1")
        lines.append(f"T1 второй SELECT (тот же BEGIN): balance = {second}")
        lines.append(
            f"Non-repeatable read: {'ДА' if first != second else 'НЕТ'} "
            f"(значение изменилось внутри транзакции T1)"
        )
        await tr1.commit()
    finally:
        await conn1.close()
        await conn2.close()

    return lines


async def demo_phantom_read() -> list[str]:
    lines: list[str] = []
    lines.append("СУБД: PostgreSQL 16, isolation READ COMMITTED")
    lines.append("Сценарий: два SELECT по department='sales', между ними INSERT+COMMIT в T2.")

    conn1 = await asyncpg.connect(PG_DSN)
    conn2 = await asyncpg.connect(PG_DSN)
    try:
        await reset_postgres(conn1)
        tr1 = conn1.transaction()
        await tr1.start()

        first = await conn1.fetch(
            "SELECT id, full_name, salary FROM employees WHERE department = 'sales' ORDER BY id"
        )
        lines.append(f"T1 первый SELECT: {len(first)} строк(и)")
        for row in first:
            lines.append(f"  - id={row['id']} name={row['full_name']} salary={row['salary']}")

        tr2 = conn2.transaction()
        await tr2.start()
        new_id = await conn2.fetchval(
            """
            INSERT INTO employees (full_name, department, salary)
            VALUES ('New Sales Hire', 'sales', 700.00)
            RETURNING id
            """
        )
        await tr2.commit()
        lines.append(f"T2: INSERT id={new_id} department=sales + COMMIT")

        second = await conn1.fetch(
            "SELECT id, full_name, salary FROM employees WHERE department = 'sales' ORDER BY id"
        )
        lines.append(f"T1 второй SELECT: {len(second)} строк(и)")
        for row in second:
            lines.append(f"  - id={row['id']} name={row['full_name']} salary={row['salary']}")
        lines.append(
            f"Phantom read: {'ДА' if len(second) > len(first) else 'НЕТ'} "
            f"(появилась новая строка в том же диапазоне)"
        )
        await tr1.commit()
    finally:
        await conn1.close()
        await conn2.close()

    return lines


async def demo_lost_update() -> list[str]:
    lines: list[str] = []
    lines.append("СУБД: PostgreSQL 16, isolation READ COMMITTED")
    lines.append("Сценарий: обе транзакции читают 1000, каждая пишет 1100 (+100), без FOR UPDATE.")

    conn1 = await asyncpg.connect(PG_DSN)
    conn2 = await asyncpg.connect(PG_DSN)
    try:
        await reset_postgres(conn1)
        tr1 = conn1.transaction()
        tr2 = conn2.transaction()
        await tr1.start()
        await tr2.start()

        b1 = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1")
        b2 = await conn2.fetchval("SELECT balance FROM accounts WHERE id = 1")
        lines.append(f"T1 SELECT: balance = {b1}")
        lines.append(f"T2 SELECT: balance = {b2}")

        await conn1.execute("UPDATE accounts SET balance = 1100.00 WHERE id = 1")
        await tr1.commit()
        lines.append("T1: UPDATE balance=1100 + COMMIT")

        await conn2.execute("UPDATE accounts SET balance = 1100.00 WHERE id = 1")
        await tr2.commit()
        lines.append("T2: UPDATE balance=1100 (от исходных 1000) + COMMIT")

        final = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1")
        lines.append(f"Итоговый balance: {final}")
        lines.append(
            f"Lost update: {'ДА' if final == 1100 else 'НЕТ'} "
            f"(ожидалось 1200 при двух инкрементах +100)"
        )
    finally:
        await conn1.close()
        await conn2.close()

    return lines


async def demo_prevention() -> list[str]:
    lines: list[str] = []
    lines.append("Проверка защиты от lost update через SELECT ... FOR UPDATE")

    conn1 = await asyncpg.connect(PG_DSN)
    conn2 = await asyncpg.connect(PG_DSN)
    try:
        await reset_postgres(conn1)
        tr1 = conn1.transaction()
        await tr1.start()
        b1 = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1 FOR UPDATE")
        lines.append(f"T1 SELECT FOR UPDATE: balance = {b1}")

        tr2 = conn2.transaction()
        await tr2.start()

        async def t2_update() -> None:
            await conn2.execute("SELECT balance FROM accounts WHERE id = 1 FOR UPDATE")
            await conn2.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 1")
            await tr2.commit()

        task = asyncio.create_task(t2_update())
        await asyncio.sleep(0.3)
        lines.append("T2 ждёт блокировку FOR UPDATE от T1...")
        await conn1.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 1")
        await tr1.commit()
        lines.append("T1: +100 и COMMIT (сняла блокировку)")
        await task

        final = await conn1.fetchval("SELECT balance FROM accounts WHERE id = 1")
        lines.append(f"Итоговый balance: {final} (ожидалось 1200)")
        lines.append(f"Потеря обновления устранена: {'ДА' if final == 1200 else 'НЕТ'}")
    finally:
        await conn1.close()
        await conn2.close()

    return lines


async def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    demos = [
        ("01_dirty_read.log", demo_dirty_read),
        ("02_non_repeatable_read.log", demo_non_repeatable_read),
        ("03_phantom_read.log", demo_phantom_read),
        ("04_lost_update.log", demo_lost_update),
        ("05_prevention.log", demo_prevention),
    ]

    for filename, fn in demos:
        print(f"Running {filename}...")
        try:
            content = await fn()
        except Exception as exc:
            print(f"FAILED {filename}: {exc}", file=sys.stderr)
            return 1
        log(content, filename.replace(".log", ""))
        (RESULTS / filename).write_text("\n".join(content), encoding="utf-8")
        print(f"  -> {RESULTS / filename}")

    combined = []
    for filename, _ in demos:
        combined.append((RESULTS / filename).read_text(encoding="utf-8"))
    (RESULTS / "all_demos.log").write_text("\n".join(combined), encoding="utf-8")
    print(f"Combined log: {RESULTS / 'all_demos.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
