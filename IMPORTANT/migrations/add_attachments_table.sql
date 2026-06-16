-- Migration: create attachments table for persistent chat-attachment storage
-- Run against production Postgres before deploying the attachment-persistence feature.
--
-- Stores ONLY the already-sanitized (PII-redacted, injection-checked) attachment
-- text produced by routers/ai/enhance.py::_sanitize_attachment_text(). The raw,
-- unsanitized attachment text is NEVER written to this table.
--
-- This is a python-ai-unified-owned table (direct Postgres write via shared/db.py),
-- mirroring the self-healing CREATE TABLE IF NOT EXISTS pattern already used by
-- routers/ai/context_docs.py for ai_context_documents. The IF NOT EXISTS guard
-- lets this statement run safely as both a one-time migration and an idempotent
-- best-effort runtime check.

CREATE TABLE IF NOT EXISTS attachments (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    filename TEXT,
    mime_type TEXT,
    sanitized_content TEXT NOT NULL,
    content_length INT NOT NULL DEFAULT 0,
    pii_redacted_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_attachments_user_id ON attachments (user_id);
CREATE INDEX IF NOT EXISTS ix_attachments_user_session ON attachments (user_id, session_id);
CREATE INDEX IF NOT EXISTS ix_attachments_created_at ON attachments (created_at DESC);

COMMENT ON TABLE attachments IS 'Sanitized chat attachment text persisted for re-display in past conversations. Never stores raw/unsanitized content. See routers/ai/enhance.py::_sanitize_attachment_text and routers/context.py GET /context/attachments.';
COMMENT ON COLUMN attachments.sanitized_content IS 'PII-redacted, injection-checked attachment text — the exact text that was sent to the LLM. Raw attachment text is never persisted.';
COMMENT ON COLUMN attachments.pii_redacted_count IS 'Count of PII pattern matches redacted during sanitization, for observability only.';
COMMENT ON COLUMN attachments.session_id IS 'Nullable — not every enhance request carries a session_id.';
