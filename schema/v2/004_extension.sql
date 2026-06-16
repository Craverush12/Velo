-- =============================================================================
-- 004_extension.sql — ThinkVelocity Extension Schema
-- Schema: extension
-- Purpose: Tables specific to the browser extension API service (:8000)
--          Currently: Extension uses shared.users + consumer tables.
--          This schema holds extension-specific operational tables only.
-- Run order: FOURTH (depends on shared and consumer)
-- Source: Server 1 (FastAPI extension-api)
-- =============================================================================

-- =============================================================================
-- NOTE ON EXTENSION ARCHITECTURE
-- The browser extension primarily reads/writes to:
--   shared.users          — user identity + auth
--   shared.user_status    — subscription gate checks
--   consumer.user_prompts — stores prompts sent via extension
--   consumer.save_enhance_prompt — enhanced prompts
--   consumer.conversation_contexts — context captured from LLM tabs
--
-- The extension schema here holds operational tables that are
-- ONLY written by the extension API service.
-- =============================================================================

CREATE TABLE IF NOT EXISTS extension.install_events (
    id              BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id         INTEGER,                           -- NULL for anonymous installs
    event_type      VARCHAR(50) NOT NULL,              -- 'install' | 'update' | 'uninstall'
    extension_version VARCHAR(20),
    browser         VARCHAR(50),
    platform        VARCHAR(50),
    cohort_key      VARCHAR(64),                       -- partner/campaign cohort
    ip_address      VARCHAR(45),
    metadata        JSONB       DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extension_install_events_pkey PRIMARY KEY (id),
    CONSTRAINT extension_install_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE SET NULL
);

COMMENT ON TABLE extension.install_events IS 'Browser extension install/update/uninstall events. SOC2 CC7.2.';

CREATE TABLE IF NOT EXISTS extension.api_sessions (
    session_id      UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id         INTEGER     NOT NULL,
    extension_version VARCHAR(20),
    browser         VARCHAR(50),
    tab_origin      TEXT,                              -- URL origin of the LLM platform tab
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_ping_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    CONSTRAINT extension_api_sessions_pkey PRIMARY KEY (session_id),
    CONSTRAINT extension_api_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

COMMENT ON TABLE extension.api_sessions IS 'Extension active sessions — used for usage analytics and rate limiting';

CREATE TABLE IF NOT EXISTS extension.feature_usage (
    id              BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id         INTEGER     NOT NULL,
    feature         VARCHAR(100) NOT NULL,             -- 'enhance' | 'refine' | 'context_capture' | 'memory_read'
    platform        VARCHAR(50),                       -- 'ChatGPT' | 'Claude' | 'Gemini' | 'Mistral'
    tokens_consumed INTEGER     DEFAULT 0,
    latency_ms      INTEGER,
    success         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extension_feature_usage_pkey PRIMARY KEY (id),
    CONSTRAINT extension_feature_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

COMMENT ON TABLE extension.feature_usage IS 'Per-feature usage counters from extension — drives analytics and rate limiting. SOC2 PI1.1.';
