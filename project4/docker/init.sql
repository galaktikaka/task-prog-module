-- PostgreSQL: схема для демонстрации аномалий изоляции
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;

CREATE TABLE accounts (
    id          INT PRIMARY KEY,
    owner_name  TEXT NOT NULL,
    balance     NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
);

CREATE TABLE employees (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    department  TEXT NOT NULL,
    salary      NUMERIC(12, 2) NOT NULL CHECK (salary > 0)
);

INSERT INTO accounts (id, owner_name, balance) VALUES
    (1, 'Alice', 1000.00),
    (2, 'Bob', 500.00);

INSERT INTO employees (full_name, department, salary) VALUES
    ('Ivan Petrov', 'sales', 800.00),
    ('Anna Kozlova', 'sales', 950.00),
    ('Pavel Sidorov', 'it', 1200.00);
