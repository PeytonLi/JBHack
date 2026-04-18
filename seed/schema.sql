-- Auto-Scribe demo schema for Supabase (Postgres)
-- Intentionally missing FK constraint on orders.warehouse_id — that's the bug.

CREATE TABLE IF NOT EXISTS warehouses (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    location    TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory (
    id           SERIAL PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    sku          TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    sku          TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    warehouse_id INTEGER NOT NULL,    -- NOTE: no FK constraint here — this is the bug
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
