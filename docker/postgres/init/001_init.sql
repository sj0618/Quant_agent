-- Local development bootstrap for Quant-Agent TimescaleDB.
-- This file is executed only when the PostgreSQL data directory is first
-- initialized by the official Docker entrypoint.

CREATE EXTENSION IF NOT EXISTS timescaledb;

DO $$
BEGIN
    RAISE NOTICE 'Quant-Agent local TimescaleDB bootstrap completed.';
END $$;

