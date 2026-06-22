-- Migration 007: external contacts for partnership and outbound (NOT Velocity users)
-- Sources: apollo / clay / manual / community
-- icp_score ranges 0.0-1.0; is_suppressed mirrors suppressions table for fast join-free reads.
-- Safe to re-run: all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS contacts (
  contact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  full_name TEXT,
  company TEXT,
  title TEXT,
  source TEXT,
  icp_score FLOAT CHECK (icp_score BETWEEN 0.0 AND 1.0),
  icp_category TEXT,
  is_suppressed BOOLEAN DEFAULT FALSE,
  enriched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}',
  CONSTRAINT contacts_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_icp_category ON contacts(icp_category);
CREATE INDEX IF NOT EXISTS idx_contacts_is_suppressed ON contacts(is_suppressed);
