-- Migration 010: execution state for scheduled workflows
-- Workflows: market_intel / lifecycle / content / outbound / analytics
-- idempotency_key prevents duplicate scheduled runs (nullable for one-off manual/webhook triggers).
-- records_processed / records_failed provide per-run progress metrics.
-- Safe to re-run: all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS workflow_runs (
  workflow_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow TEXT NOT NULL,
  idempotency_key TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','killed')),
  trigger TEXT CHECK (trigger IN ('schedule','webhook','manual')),
  records_processed INT DEFAULT 0,
  records_failed INT DEFAULT 0,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  metadata JSONB DEFAULT '{}',
  CONSTRAINT workflow_runs_idempotency_unique UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at DESC);
