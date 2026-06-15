-- Migration: add prompt_suffix to tenants table for per-tenant system prompt overrides
-- Run against production Postgres before deploying the tenant prompt suffix feature.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS prompt_suffix TEXT;
COMMENT ON COLUMN tenants.prompt_suffix IS 'Optional text appended to system prompt for enterprise tenant brand voice / constraints. Max 2000 chars recommended.';
