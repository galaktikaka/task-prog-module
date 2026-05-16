-- Как избежать аномалий (PostgreSQL)

-- 1) Dirty read: в PostgreSQL не возникает (READ UNCOMMITTED = READ COMMITTED).
--    В MySQL — не использовать READ UNCOMMITTED; держать READ COMMITTED+.

-- 2) Non-repeatable read: REPEATABLE READ или SERIALIZABLE
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM accounts WHERE id = 1;
-- параллельное изменение другой сессией не видно при повторном SELECT
SELECT balance FROM accounts WHERE id = 1;
COMMIT;

-- 3) Phantom read: REPEATABLE READ (в PG снимок на транзакцию) или SERIALIZABLE
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM employees WHERE department = 'sales';
-- INSERT другой сессией не попадёт в повторный COUNT
SELECT COUNT(*) FROM employees WHERE department = 'sales';
COMMIT;

-- 4) Lost update: pessimistic lock
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- вторая сессия ждёт на том же SELECT ... FOR UPDATE
UPDATE accounts SET balance = balance + 100 WHERE id = 1;
COMMIT;

-- 4) Lost update: optimistic lock (версия)
-- ALTER TABLE accounts ADD COLUMN version INT NOT NULL DEFAULT 0;
-- UPDATE accounts SET balance = $new, version = version + 1
-- WHERE id = 1 AND version = $expected;
