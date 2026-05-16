-- Сброс данных PostgreSQL перед повторным прогоном
TRUNCATE employees RESTART IDENTITY CASCADE;
TRUNCATE accounts RESTART IDENTITY CASCADE;

INSERT INTO accounts (id, owner_name, balance) VALUES
    (1, 'Alice', 1000.00),
    (2, 'Bob', 500.00);

INSERT INTO employees (full_name, department, salary) VALUES
    ('Ivan Petrov', 'sales', 800.00),
    ('Anna Kozlova', 'sales', 950.00),
    ('Pavel Sidorov', 'it', 1200.00);
