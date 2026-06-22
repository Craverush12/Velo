-- Migration 009: log of every automated agent action
-- Agents: content_drafting / funnel_audit / weekly_performance / lead_qual / market_intel
-- campaign_id FK uses ON DELETE SET NULL so deleting a campaign does not wipe history.
-- cost_usd tracks LLM token spend per run for budget reporting.
-- Safe to re-run: all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '1.0.0',
  campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE SET NULL,
  input_summary JSONB DEFAULT '{}',
  output_summary JSONB DEFAULT '{}',
  confidence FLOAT CHECK (confidence BETWEEN 0.0 AND 1.0),
  decision TEXT,
  warnings JSONB DEFAULT '[]',
  status TEXT DEFAULT 'running' CHECK (status IN ('running','completed','failed','killed')),
  cost_usd FLOAT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_campaign_id ON agent_runs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at ON agent_runs(started_at DESC);
