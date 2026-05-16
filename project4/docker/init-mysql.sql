-- MySQL: таблица для dirty read (PostgreSQL dirty read не допускает)
CREATE TABLE IF NOT EXISTS accounts (
    id          INT PRIMARY KEY,
    owner_name  VARCHAR(100) NOT NULL,
    balance     DECIMAL(12, 2) NOT NULL
);

INSERT INTO accounts (id, owner_name, balance) VALUES
    (1, 'Alice', 1000.00)
ON DUPLICATE KEY UPDATE owner_name = VALUES(owner_name), balance = VALUES(balance);
