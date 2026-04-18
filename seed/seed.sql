-- Seed data for Auto-Scribe demo
-- Run after schema.sql

-- Valid warehouses
INSERT INTO warehouses (id, name, location) VALUES
    (1, 'East Coast Fulfillment', 'Newark, NJ'),
    (2, 'West Coast Fulfillment', 'Compton, CA')
ON CONFLICT (id) DO NOTHING;

-- Inventory in valid warehouses
INSERT INTO inventory (warehouse_id, sku, quantity) VALUES
    (1, 'WIDGET-001', 500),
    (1, 'GADGET-002', 200),
    (2, 'WIDGET-001', 300),
    (2, 'GADGET-002', 150)
ON CONFLICT DO NOTHING;

-- Normal orders (valid warehouse_id)
INSERT INTO orders (id, user_id, sku, quantity, warehouse_id, status) VALUES
    ('ORDER-001', 'user_alice', 'WIDGET-001', 2, 1, 'fulfilled'),
    ('ORDER-002', 'user_bob',   'GADGET-002', 1, 2, 'pending')
ON CONFLICT (id) DO NOTHING;

-- THE POISON ROW: warehouse_id=999 does not exist in warehouses
-- This is the row that crashes POST /checkout
INSERT INTO orders (id, user_id, sku, quantity, warehouse_id, status) VALUES
    ('POISON-001', 'user_charlie', 'WIDGET-001', 1, 999, 'pending')
ON CONFLICT (id) DO NOTHING;
