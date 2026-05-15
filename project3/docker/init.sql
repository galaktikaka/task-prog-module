-- Начальные данные: 500 ключей для единого теста
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO items (id, value, updated_at)
SELECT gs, 'seed-' || gs::text, NOW()
FROM generate_series(1, 500) AS gs
ON CONFLICT (id) DO NOTHING;
