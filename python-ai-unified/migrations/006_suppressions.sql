-- Migration 006: global contact block list
-- Stores emails that must never be contacted regardless of campaign.
-- Reasons: unsubscribe / bounce / complaint / manual override / duplicate detection.
-- Safe to re-run: all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS suppressions (
  suppression_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT        NOT NULL,
  reason          TEXT        CHECK (reason IN ('unsubscribe','bounce','complaint','manual','duplicate')),
  source          TEXT,                          -- which system added it: brevo/outbound/manual
  suppressed_at   TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ,
  CONSTRAINT suppressions_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_suppressions_email  ON suppressions(email);
CREATE INDEX IF NOT EXISTS idx_suppressions_reason ON suppressions(reason);
