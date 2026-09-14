-- Lineage writes are current-state upserts keyed by target/source identity.
-- Apply this only after existing duplicate lineage rows have been compacted.
-- This file intentionally has no transaction wrapper because CONCURRENTLY
-- cannot run inside a transaction block.

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_lineage_event_logical_edge
    ON meta.lineage_event (target_table, target_key, source_table, source_key);
