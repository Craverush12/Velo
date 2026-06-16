-- =============================================================================
-- 001_shared.sql — ThinkVelocity Consolidated Schema
-- Schema: shared
-- Purpose: Tables used by multiple services (Node.js consumer backend,
--          Python AI, Extension API). Core auth and user identity.
-- Run order: FIRST (no dependencies)
-- SOC2: CC6.1 (logical access), CC6.2 (authentication), CC6.3 (authorization)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS shared;
CREATE SCHEMA IF NOT EXISTS consumer;
CREATE SCHEMA IF NOT EXISTS enterprise;
CREATE SCHEMA IF NOT EXISTS extension;

-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for embeddings

COMMENT ON SCHEMA shared IS 'Core identity and auth tables — used by all services';
COMMENT ON SCHEMA consumer IS 'Consumer product (thinkvelocity.in) tables';
COMMENT ON SCHEMA enterprise IS 'Enterprise product (enterprise.thinkvelocity.in) tables';
COMMENT ON SCHEMA extension IS 'Browser extension API tables';

-- =============================================================================
-- TYPES
-- =============================================================================

-- (none in shared — types defined per-schema below)

-- =============================================================================
-- shared.users — canonical user identity record
-- Source: localpgvelocity.public.usertable
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.users_user_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.users (
    user_id           INTEGER     NOT NULL DEFAULT nextval('shared.users_user_id_seq'),
    name              VARCHAR(255) NOT NULL,
    email             VARCHAR(255) NOT NULL,
    password          VARCHAR(255),                        -- bcrypt hash; NULL for OAuth users
    google_id         VARCHAR(255),
    profile_img_url   TEXT,
    occupation        VARCHAR(255),
    llm_platform      VARCHAR(100),
    tutorial          BOOLEAN     DEFAULT FALSE,
    email_verified    BOOLEAN     DEFAULT FALSE,
    installed         BOOLEAN,                             -- extension installed flag
    onboarding_completed BOOLEAN  DEFAULT FALSE,
    consumer_partner_cohort VARCHAR(64),                  -- external cohort key (e.g. VGYR)
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT shared_users_pkey PRIMARY KEY (user_id),
    CONSTRAINT shared_users_email_key UNIQUE (email),
    CONSTRAINT shared_users_google_id_key UNIQUE (google_id)
);

COMMENT ON TABLE shared.users IS 'Canonical user record — source of truth for identity across all services';
COMMENT ON COLUMN shared.users.consumer_partner_cohort IS 'Optional external consumer cohort key (e.g. VGYR). Set via SQL, admin, or optional ext-install body.';
COMMENT ON COLUMN shared.users.installed IS 'True when user has installed the browser extension';

ALTER SEQUENCE shared.users_user_id_seq OWNED BY shared.users.user_id;

-- =============================================================================
-- shared.user_status — subscription tier and trial state
-- Source: localpgvelocity.public.userstatus
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.user_status_status_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.user_status (
    status_id         INTEGER     NOT NULL DEFAULT nextval('shared.user_status_status_id_seq'),
    user_id           INTEGER     NOT NULL,
    status            VARCHAR(50) NOT NULL DEFAULT 'free',
    count             INTEGER     NOT NULL DEFAULT 5,
    trial_started_at  TIMESTAMP,
    trial_ended_at    TIMESTAMP,
    has_used_trial    BOOLEAN     DEFAULT FALSE,
    created_at        TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT shared_user_status_pkey PRIMARY KEY (status_id),
    CONSTRAINT shared_user_status_user_id_key UNIQUE (user_id),
    CONSTRAINT shared_user_status_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_user_status_count CHECK (count >= 0),
    CONSTRAINT chk_user_status_status CHECK (status IN ('freetrial', 'free', 'pro')),
    CONSTRAINT chk_user_status_trial_dates CHECK (
        trial_started_at IS NULL OR trial_ended_at IS NULL OR trial_ended_at > trial_started_at
    )
);

ALTER SEQUENCE shared.user_status_status_id_seq OWNED BY shared.user_status.status_id;

COMMENT ON TABLE shared.user_status IS 'User subscription status and trial management — used by Node.js backend and Python AI for gate-keeping';
COMMENT ON COLUMN shared.user_status.status IS 'freetrial | free | pro';
COMMENT ON COLUMN shared.user_status.count IS 'Remaining uses for current period';

-- =============================================================================
-- shared.refresh_tokens — JWT refresh token store (SOC2: CC6.2)
-- Source: localpgvelocity.public.refresh_tokens
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.refresh_tokens_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.refresh_tokens (
    id            INTEGER     NOT NULL DEFAULT nextval('shared.refresh_tokens_id_seq'),
    user_id       INTEGER     NOT NULL,
    token_id      UUID        NOT NULL,
    token_hash    VARCHAR(255) NOT NULL,
    expires_at    TIMESTAMP   NOT NULL,
    created_at    TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    last_used_at  TIMESTAMP,
    revoked       BOOLEAN     DEFAULT FALSE,
    device_info   JSONB,
    ip_address    VARCHAR(45),
    CONSTRAINT shared_refresh_tokens_pkey PRIMARY KEY (id),
    CONSTRAINT shared_refresh_tokens_token_id_key UNIQUE (token_id),
    CONSTRAINT shared_refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

ALTER SEQUENCE shared.refresh_tokens_id_seq OWNED BY shared.refresh_tokens.id;

COMMENT ON TABLE shared.refresh_tokens IS 'JWT refresh tokens — rotated on use, revokable per-device. SOC2 CC6.2.';

-- =============================================================================
-- shared.otp_verification — email OTP codes (SOC2: CC6.2)
-- Source: localpgvelocity.public.otp_verification
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.otp_verification_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.otp_verification (
    id         INTEGER      NOT NULL DEFAULT nextval('shared.otp_verification_id_seq'),
    user_id    INTEGER,
    email      VARCHAR(255) NOT NULL,
    otp        VARCHAR(10)  NOT NULL,
    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP    GENERATED ALWAYS AS (created_at + INTERVAL '10 minutes') STORED,
    CONSTRAINT shared_otp_verification_pkey PRIMARY KEY (id)
);

ALTER SEQUENCE shared.otp_verification_id_seq OWNED BY shared.otp_verification.id;

-- =============================================================================
-- shared.password_reset_tokens — password reset flow (SOC2: CC6.2)
-- Source: localpgvelocity.public.password_reset_tokens
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.password_reset_tokens_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.password_reset_tokens (
    id          INTEGER      NOT NULL DEFAULT nextval('shared.password_reset_tokens_id_seq'),
    user_id     INTEGER      NOT NULL,
    email       VARCHAR(255) NOT NULL,
    reset_token VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP    DEFAULT (CURRENT_TIMESTAMP + INTERVAL '15 minutes'),
    CONSTRAINT shared_password_reset_tokens_pkey PRIMARY KEY (id),
    CONSTRAINT shared_password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

ALTER SEQUENCE shared.password_reset_tokens_id_seq OWNED BY shared.password_reset_tokens.id;

-- =============================================================================
-- shared.all_emails — unified email collection for marketing
-- Source: localpgvelocity.public.all_emails
-- =============================================================================

CREATE SEQUENCE IF NOT EXISTS shared.all_emails_id_seq AS INTEGER START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS shared.all_emails (
    id    INTEGER      NOT NULL DEFAULT nextval('shared.all_emails_id_seq'),
    email VARCHAR(255) NOT NULL,
    ref   VARCHAR(255),
    CONSTRAINT shared_all_emails_pkey PRIMARY KEY (id),
    CONSTRAINT shared_all_emails_email_key UNIQUE (email)
);

ALTER SEQUENCE shared.all_emails_id_seq OWNED BY shared.all_emails.id;

-- =============================================================================
-- TRIGGERS — shared schema
-- =============================================================================

CREATE OR REPLACE FUNCTION shared.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON shared.users
    FOR EACH ROW EXECUTE FUNCTION shared.set_updated_at();

CREATE TRIGGER trg_user_status_updated_at
    BEFORE UPDATE ON shared.user_status
    FOR EACH ROW EXECUTE FUNCTION shared.set_updated_at();
