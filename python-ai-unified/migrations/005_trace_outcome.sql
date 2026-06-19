-- Migration 005: outcome signal for prompt_traces
-- Closes the loop: did the enhanced prompt actually get used / work?
-- Values: copied | reenhanced | thumbs_up | thumbs_down | ignored

ALTER TABLE prompt_traces ADD COLUMN IF NOT EXISTS outcome     TEXT;
ALTER TABLE prompt_traces ADD COLUMN IF NOT EXISTS outcome_at  TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_traces_outcome
    ON prompt_traces (outcome) WHERE outcome IS NOT NULL;
