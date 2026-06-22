-- Migration 008: acquisition, lifecycle, or content campaign initiatives
-- Types: outbound / lifecycle / content / partnership
-- Status lifecycle: draft -> active -> paused / completed / killed
-- kill_rule is a free-text policy expression evaluated by the funnel_audit agent.
-- Safe to re-run: all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('outbound','lifecycle','content','partnership')),
  icp_target TEXT,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft','active','paused','completed','killed')),
  owner TEXT,
  daily_limit INT,
  kill_rule TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_type ON campaigns(type);
