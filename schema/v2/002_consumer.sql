-- =============================================================================
-- 002_consumer.sql — ThinkVelocity Consumer Schema
-- Schema: consumer
-- Purpose: All tables for the consumer product (thinkvelocity.in)
--          Served by: Node.js backend (:3005), Python AI (:8005), Extension (:8000)
-- Run order: SECOND (depends on shared schema)
-- Source DB: localpgvelocity (54 tables → minus 6 shared = 48 consumer tables)
-- =============================================================================

-- =============================================================================
-- EXTENSIONS (if not already created by 001_shared.sql)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

CREATE TYPE consumer.content_type_enum AS ENUM ('input', 'response');

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION consumer.normalize_enhance_fields()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.mode = LOWER(TRIM(NEW.mode));
  NEW.platform_source = LOWER(TRIM(NEW.platform_source));
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.normalize_enhance_mode()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.mode IS NOT NULL THEN
    NEW.mode = LOWER(TRIM(NEW.mode));
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.set_updated_at_and_count()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := NOW();
  NEW.update_count := COALESCE(OLD.update_count, 0) + 1;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.block_payment_downtime_events()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.event_type LIKE 'payment.downtime%' THEN
    RETURN NULL;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.cleanup_expired_reservations()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
  affected_count INTEGER;
BEGIN
  UPDATE consumer.token_reservations
  SET status = 'expired', released_at = NOW()
  WHERE status = 'pending' AND expires_at < NOW();
  GET DIAGNOSTICS affected_count = ROW_COUNT;
  RETURN affected_count;
END;
$$;

CREATE OR REPLACE FUNCTION consumer.update_enhanced_prompt_tsv()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.enhanced_prompt_tsv := to_tsvector('english', NEW.enhanced_prompt);
  RETURN NEW;
END;
$$;

-- =============================================================================
-- BILLING & SUBSCRIPTIONS
-- Note: billing_plans has no FK to users, so create first
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.billing_plans (
    id                       UUID         NOT NULL DEFAULT gen_random_uuid(),
    code                     TEXT         NOT NULL,
    name                     TEXT         NOT NULL,
    interval                 TEXT         NOT NULL,
    interval_count           INTEGER      NOT NULL DEFAULT 1,
    amount                   INTEGER      NOT NULL,
    currency                 TEXT         NOT NULL DEFAULT 'INR',
    razorpay_plan_id         TEXT,
    is_active                BOOLEAN      NOT NULL DEFAULT TRUE,
    monthly_token_allowance  INTEGER      DEFAULT 0,
    standard_mode_unlimited  BOOLEAN      DEFAULT TRUE,
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT consumer_billing_plans_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_billing_plans_code_key UNIQUE (code),
    CONSTRAINT consumer_billing_plans_razorpay_plan_id_key UNIQUE (razorpay_plan_id),
    CONSTRAINT consumer_billing_plans_interval_check CHECK (interval IN ('month', 'year'))
);

COMMENT ON TABLE consumer.billing_plans IS 'Subscription plans (Monthly, Yearly)';
COMMENT ON COLUMN consumer.billing_plans.amount IS 'Amount in minor units (paise for INR)';

CREATE TABLE IF NOT EXISTS consumer.token_packages (
    id            UUID    NOT NULL DEFAULT gen_random_uuid(),
    code          TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    description   TEXT,
    currency      TEXT    NOT NULL,
    price_cents   INTEGER NOT NULL,
    tokens        INTEGER NOT NULL,
    bonus_tokens  INTEGER DEFAULT 0,
    is_popular    BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    badge_text    TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    metadata      JSONB   DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_token_packages_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_token_packages_code_key UNIQUE (code)
);

COMMENT ON TABLE consumer.token_packages IS 'Purchasable token packages with multi-currency support';

CREATE TABLE IF NOT EXISTS consumer.feature_token_costs (
    id              UUID    NOT NULL DEFAULT gen_random_uuid(),
    feature_code    TEXT    NOT NULL,
    feature_name    TEXT    NOT NULL,
    tokens_per_use  INTEGER NOT NULL DEFAULT 4,
    free_for_pro    BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_feature_token_costs_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_feature_token_costs_feature_code_key UNIQUE (feature_code)
);

COMMENT ON TABLE consumer.feature_token_costs IS 'Per-feature token pricing configuration';

CREATE TABLE IF NOT EXISTS consumer.subscriptions (
    id                      UUID    NOT NULL DEFAULT gen_random_uuid(),
    user_id                 INTEGER NOT NULL,
    plan_id                 UUID    NOT NULL,
    status                  TEXT    NOT NULL,
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_at               TIMESTAMPTZ,
    canceled_at             TIMESTAMPTZ,
    trial_end               TIMESTAMPTZ,
    razorpay_subscription_id TEXT,
    notes                   JSONB   DEFAULT '{}',
    last_token_grant_at     TIMESTAMPTZ,
    tokens_granted_this_period INTEGER DEFAULT 0,
    monthly_token_allowance INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_subscriptions_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES consumer.billing_plans(id)
);

COMMENT ON TABLE consumer.subscriptions IS 'User subscription lifecycle';
COMMENT ON COLUMN consumer.subscriptions.status IS 'draft | created | authenticated | active | past_due | halted | canceled | completed';

CREATE TABLE IF NOT EXISTS consumer.payments (
    id                   UUID    NOT NULL DEFAULT gen_random_uuid(),
    user_id              INTEGER NOT NULL,
    subscription_id      UUID,
    razorpay_payment_id  TEXT,
    razorpay_invoice_id  TEXT,
    amount               INTEGER NOT NULL,
    currency             TEXT    NOT NULL DEFAULT 'INR',
    status               TEXT    NOT NULL,
    error_code           TEXT,
    error_description    TEXT,
    captured_at          TIMESTAMPTZ,
    raw                  JSONB   DEFAULT '{}',
    payment_type         TEXT    DEFAULT 'subscription',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_payments_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_payments_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES consumer.subscriptions(id),
    CONSTRAINT consumer_payments_payment_type_check CHECK (payment_type IN ('subscription', 'token_purchase'))
);

COMMENT ON COLUMN consumer.payments.amount IS 'Amount in minor units (paise for INR)';

CREATE TABLE IF NOT EXISTS consumer.webhook_events (
    id                  UUID    NOT NULL DEFAULT gen_random_uuid(),
    event_type          TEXT    NOT NULL,
    razorpay_event_id   TEXT,
    signature_valid     BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT    NOT NULL DEFAULT 'received',
    retry_count         INTEGER NOT NULL DEFAULT 0,
    payload             JSONB   NOT NULL,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_webhook_events_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_webhook_events_razorpay_event_id_key UNIQUE (razorpay_event_id)
);

COMMENT ON TABLE consumer.webhook_events IS 'Razorpay webhook events — idempotency audit trail. SOC2 PI1.1.';

-- Token economy
CREATE TABLE IF NOT EXISTS consumer.token_ledger (
    id               UUID    NOT NULL DEFAULT gen_random_uuid(),
    user_id          INTEGER NOT NULL,
    token_type       TEXT    NOT NULL,
    source_id        UUID,
    source_reference TEXT,
    initial_amount   INTEGER NOT NULL,
    current_amount   INTEGER NOT NULL DEFAULT 0,
    balance_after    INTEGER,
    expires_at       TIMESTAMPTZ,
    metadata         JSONB   DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_token_ledger_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_token_ledger_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_token_ledger_token_type_check CHECK (token_type IN ('subscription', 'purchased', 'referral', 'coupon', 'bonus', 'compensation', 'legacy')),
    CONSTRAINT consumer_token_ledger_positive_initial CHECK (initial_amount > 0),
    CONSTRAINT consumer_token_ledger_non_negative_current CHECK (current_amount >= 0),
    CONSTRAINT consumer_token_ledger_current_not_exceed CHECK (current_amount <= initial_amount)
);

COMMENT ON TABLE consumer.token_ledger IS 'Token ownership by type with expiration. SOC2 PI1.1.';

CREATE TABLE IF NOT EXISTS consumer.token_transactions (
    id               UUID    NOT NULL DEFAULT gen_random_uuid(),
    user_id          INTEGER NOT NULL,
    ledger_id        UUID,
    transaction_type TEXT    NOT NULL,
    amount           INTEGER NOT NULL,
    balance_before   INTEGER NOT NULL,
    balance_after    INTEGER NOT NULL,
    reference_type   TEXT,
    reference_id     TEXT,
    description      TEXT,
    metadata         JSONB   DEFAULT '{}',
    idempotency_key  TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_token_transactions_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_token_transactions_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT consumer_token_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_token_transactions_ledger_id_fkey FOREIGN KEY (ledger_id) REFERENCES consumer.token_ledger(id),
    CONSTRAINT consumer_token_transactions_type_check CHECK (transaction_type IN ('credit', 'debit', 'expire', 'revoke', 'refund', 'adjustment'))
);

COMMENT ON TABLE consumer.token_transactions IS 'Full audit trail of token movements. SOC2 PI1.1.';

CREATE TABLE IF NOT EXISTS consumer.token_reservations (
    id           UUID    NOT NULL DEFAULT gen_random_uuid(),
    user_id      INTEGER NOT NULL,
    amount       INTEGER NOT NULL,
    feature_code TEXT,
    status       TEXT    NOT NULL DEFAULT 'pending',
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '5 minutes'),
    created_at   TIMESTAMPTZ DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    released_at  TIMESTAMPTZ,
    CONSTRAINT consumer_token_reservations_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_token_reservations_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_token_reservations_status_check CHECK (status IN ('pending', 'confirmed', 'released', 'expired'))
);

COMMENT ON TABLE consumer.token_reservations IS 'Temporary token locks for concurrent safety';

-- =============================================================================
-- PROMPT TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.user_prompts (
    prompt_id       VARCHAR(255) NOT NULL,
    user_id         INTEGER      NOT NULL,
    user_prompt     TEXT         NOT NULL,
    conversation_id UUID,
    platform        VARCHAR(50)  DEFAULT 'ChatGPT',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_user_prompts_pkey PRIMARY KEY (prompt_id),
    CONSTRAINT consumer_user_prompts_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_user_prompts_platform_lowercase CHECK (platform = lower(platform))
);

CREATE TABLE IF NOT EXISTS consumer.save_enhance_prompt (
    enhanced_prompt_id  VARCHAR(255) NOT NULL,
    prompt_id           VARCHAR(255) NOT NULL,
    enhanced_prompt     TEXT         NOT NULL,
    processing_time     NUMERIC,
    intent              VARCHAR(100),
    llm_used            VARCHAR(100),
    complexity          VARCHAR(50),
    domain              VARCHAR(100),
    mode                VARCHAR(50),
    user_status         VARCHAR(20),
    feedback            INTEGER      DEFAULT 0,
    user_id             INTEGER,
    conversation_id     UUID,
    input_token         INTEGER,
    output_token        INTEGER,
    total_token         INTEGER,
    annotated_segments  JSONB,
    metadata            JSONB,
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_save_enhance_prompt_pkey PRIMARY KEY (enhanced_prompt_id),
    CONSTRAINT consumer_save_enhance_prompt_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS consumer.refine_prompt (
    refine_id          VARCHAR(255) NOT NULL,
    prompt_id          VARCHAR(255) NOT NULL,
    enhanced_prompt_id VARCHAR(255) NOT NULL,
    refine_question_1  TEXT,
    refine_question_2  TEXT,
    refine_question_3  TEXT,
    refine_question_4  TEXT,
    refine_answer_1    TEXT,
    refine_answer_2    TEXT,
    refine_answer_3    TEXT,
    refine_answer_4    TEXT,
    refined_prompt     TEXT         NOT NULL,
    processing_time    NUMERIC,
    feedback           INTEGER      DEFAULT 0,
    user_id            INTEGER,
    conversation_id    UUID,
    input_token        INTEGER,
    output_token       INTEGER,
    total_token        INTEGER,
    annotated_segments JSONB,
    created_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_refine_prompt_pkey PRIMARY KEY (refine_id),
    CONSTRAINT consumer_refine_prompt_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS consumer.prompt_history (
    prompt_id       INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id         INTEGER      NOT NULL,
    content_type    VARCHAR(50),
    prompt          TEXT,
    ref_prompt_id   INTEGER,
    ai_type         VARCHAR(100),
    selected_style  VARCHAR(100),
    tokens_used     INTEGER,
    deleted         BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMPTZ  DEFAULT now(),
    updated_at      TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_prompt_history_pkey PRIMARY KEY (prompt_id),
    CONSTRAINT consumer_prompt_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.prompt_preferences (
    id                 INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id            INTEGER NOT NULL,
    word_count         VARCHAR(50),
    custom_instructions TEXT,
    template           VARCHAR(100),
    language           VARCHAR(50),
    complexity         VARCHAR(50),
    output_format      VARCHAR(100),
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_prompt_preferences_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_prompt_preferences_user_id_key UNIQUE (user_id),
    CONSTRAINT consumer_prompt_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

-- =============================================================================
-- MARKETPLACE
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.prompt_marketplace (
    marketplace_prompt_id INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    prompt_title          VARCHAR(500),
    prompt_content        TEXT,
    intent                VARCHAR(255),
    domain                VARCHAR(255),
    sub_domain            VARCHAR(255),
    context               TEXT,
    platform              VARCHAR(100),
    llm_model             VARCHAR(100),
    complexity            VARCHAR(50),
    attachment            VARCHAR(100),
    mode                  VARCHAR(50),
    img_url               TEXT,
    is_deleted            BOOLEAN      DEFAULT FALSE,
    created_at            TIMESTAMPTZ  DEFAULT now(),
    updated_at            TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_prompt_marketplace_pkey PRIMARY KEY (marketplace_prompt_id)
);

CREATE TABLE IF NOT EXISTS consumer.marketplace_prompt_content_embedding (
    prompt_content_embedding_id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    marketplace_prompt_id       INTEGER NOT NULL,
    prompt_content_embedding    BYTEA,
    metadata                    JSONB,
    created_at                  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_mkt_embedding_pkey PRIMARY KEY (prompt_content_embedding_id),
    CONSTRAINT consumer_mkt_embedding_prompt_id_fkey FOREIGN KEY (marketplace_prompt_id) REFERENCES consumer.prompt_marketplace(marketplace_prompt_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.prompt_memory (
    prompt_memory_id      INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    marketplace_prompt_id INTEGER NOT NULL,
    user_id               INTEGER NOT NULL,
    created_at            TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_prompt_memory_pkey PRIMARY KEY (prompt_memory_id),
    CONSTRAINT consumer_prompt_memory_unique UNIQUE (marketplace_prompt_id, user_id),
    CONSTRAINT consumer_prompt_memory_prompt_id_fkey FOREIGN KEY (marketplace_prompt_id) REFERENCES consumer.prompt_marketplace(marketplace_prompt_id) ON DELETE CASCADE,
    CONSTRAINT consumer_prompt_memory_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.prompt_actions (
    user_id               INTEGER     NOT NULL,
    action                VARCHAR(50) NOT NULL,
    marketplace_prompt_id INTEGER     NOT NULL,
    performed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_prompt_actions_pkey PRIMARY KEY (user_id, action, marketplace_prompt_id),
    CONSTRAINT consumer_prompt_actions_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_prompt_actions_prompt_id_fkey FOREIGN KEY (marketplace_prompt_id) REFERENCES consumer.prompt_marketplace(marketplace_prompt_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.prompt_library_items (
    id               UUID    NOT NULL DEFAULT gen_random_uuid(),
    slug             TEXT    NOT NULL,
    title            TEXT    NOT NULL,
    short_prompt     TEXT,
    prompt           TEXT    NOT NULL,
    why_it_works     TEXT,
    tags             TEXT[]  NOT NULL DEFAULT '{}',
    category         TEXT    NOT NULL DEFAULT 'General',
    cover_url        TEXT,
    image_name       TEXT,
    access_tier      TEXT    NOT NULL DEFAULT 'free',
    is_pro_only      BOOLEAN NOT NULL DEFAULT FALSE,
    word_count       INTEGER,
    has_placeholders BOOLEAN NOT NULL DEFAULT FALSE,
    length_band      TEXT,
    source           TEXT    NOT NULL DEFAULT 'internal',
    source_url       TEXT,
    external_id      TEXT,
    status           TEXT    NOT NULL DEFAULT 'published',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_prompt_library_items_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_prompt_library_items_slug_key UNIQUE (slug),
    CONSTRAINT consumer_prompt_library_items_access_tier_check CHECK (access_tier IN ('free', 'pro')),
    CONSTRAINT consumer_prompt_library_items_length_band_check CHECK (length_band IN ('Short', 'Medium', 'Long')),
    CONSTRAINT consumer_prompt_library_items_status_check CHECK (status IN ('draft', 'published', 'hidden'))
);

-- =============================================================================
-- COLLECTIONS & SHARING
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.prompt_collections (
    collection_id    UUID         NOT NULL DEFAULT gen_random_uuid(),
    user_id          INTEGER      NOT NULL,
    name             VARCHAR(255) NOT NULL,
    description      TEXT,
    tag              VARCHAR(100),
    background_image VARCHAR(500),
    created_at       TIMESTAMPTZ  DEFAULT now(),
    updated_at       TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_prompt_collections_pkey PRIMARY KEY (collection_id),
    CONSTRAINT consumer_prompt_collections_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.collection_prompts (
    id                 INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    collection_id      UUID         NOT NULL,
    enhanced_prompt_id VARCHAR(255) NOT NULL,
    created_at         TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_collection_prompts_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_collection_prompts_unique UNIQUE (collection_id, enhanced_prompt_id),
    CONSTRAINT consumer_collection_prompts_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES consumer.prompt_collections(collection_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.shared_prompts (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    share_token         VARCHAR(32)  NOT NULL,
    shared_by_user_id   INTEGER      NOT NULL,
    enhanced_prompt_id  VARCHAR(255),
    refine_id           VARCHAR(255),
    user_prompt         TEXT         NOT NULL,
    enhanced_prompt     TEXT         NOT NULL,
    ai_type             VARCHAR(100),
    selected_style      VARCHAR(100),
    share_message       TEXT,
    view_count          INTEGER      DEFAULT 0,
    claim_count         INTEGER      DEFAULT 0,
    is_active           BOOLEAN      DEFAULT TRUE,
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  DEFAULT now(),
    updated_at          TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_shared_prompts_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_shared_prompts_share_token_key UNIQUE (share_token),
    CONSTRAINT consumer_shared_prompts_user_id_fkey FOREIGN KEY (shared_by_user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.shared_prompt_claims (
    id                       INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    shared_prompt_id         UUID         NOT NULL,
    claimed_by_user_id       INTEGER      NOT NULL,
    collection_id            UUID,
    claimed_enhanced_prompt_id VARCHAR(255),
    claimed_at               TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_shared_prompt_claims_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_shared_prompt_claims_prompt_id_fkey FOREIGN KEY (shared_prompt_id) REFERENCES consumer.shared_prompts(id) ON DELETE CASCADE,
    CONSTRAINT consumer_shared_prompt_claims_user_id_fkey FOREIGN KEY (claimed_by_user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

-- =============================================================================
-- CONVERSATIONS (web chat)
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.conversations (
    conversation_id UUID         NOT NULL DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL,
    title           VARCHAR(255),
    is_deleted      BOOLEAN      DEFAULT FALSE,
    is_pinned       BOOLEAN      DEFAULT FALSE,
    last_message_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_conversations_pkey PRIMARY KEY (conversation_id)
);

CREATE TABLE IF NOT EXISTS consumer.conversation_messages (
    message_id         UUID        NOT NULL DEFAULT gen_random_uuid(),
    conversation_id    UUID        NOT NULL,
    role               VARCHAR(20) NOT NULL,
    content            TEXT        NOT NULL,
    prompt_id          VARCHAR(255),
    enhanced_prompt_id VARCHAR(255),
    refine_id          VARCHAR(255),
    tokens_used        INTEGER     DEFAULT 0,
    processing_time    DOUBLE PRECISION,
    metadata           JSONB       DEFAULT '{}',
    is_deleted         BOOLEAN     DEFAULT FALSE,
    created_at         TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_conversation_messages_pkey PRIMARY KEY (message_id),
    CONSTRAINT consumer_conversation_messages_conv_id_fkey FOREIGN KEY (conversation_id) REFERENCES consumer.conversations(conversation_id) ON DELETE CASCADE,
    CONSTRAINT consumer_conversation_messages_role_check CHECK (role IN ('user', 'assistant', 'system'))
);

-- =============================================================================
-- CONTEXT ENGINE
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.conversation_contexts (
    id          UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id     INTEGER     NOT NULL,
    session_id  TEXT        NOT NULL,
    platform    TEXT        NOT NULL,
    messages    JSONB       NOT NULL,
    url         TEXT,
    raw_content JSONB,
    summary     TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_conversation_contexts_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_conversation_contexts_user_session_key UNIQUE (user_id, session_id),
    CONSTRAINT consumer_conversation_contexts_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

COMMENT ON TABLE consumer.conversation_contexts IS 'Conversation context from LLM platforms (ChatGPT, Claude, Gemini, Mistral)';

CREATE TABLE IF NOT EXISTS consumer.processed_contexts (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    user_id             VARCHAR(255) NOT NULL,
    session_id          VARCHAR(255) NOT NULL,
    essence             TEXT         NOT NULL,
    intent              VARCHAR(100) NOT NULL,
    domains             TEXT[]       NOT NULL,
    embedding           vector(1024) NOT NULL,
    embedding_model     VARCHAR(100) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    embedding_version   VARCHAR(50)  NOT NULL DEFAULT '1.0',
    message_count       INTEGER      NOT NULL,
    platform            VARCHAR(50)  NOT NULL,
    processing_strategy VARCHAR(50),
    actual_cost         NUMERIC(10,6),
    model_used          VARCHAR(100),
    tokens_used         INTEGER,
    topic_shift_analysis JSONB,
    essence_deleted     SMALLINT     NOT NULL DEFAULT 0,
    version             INTEGER      DEFAULT 1,
    processed_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT consumer_processed_contexts_pkey PRIMARY KEY (id)
);

COMMENT ON TABLE consumer.processed_contexts IS 'Processed and embedded conversation context — context engine output';

CREATE TABLE IF NOT EXISTS consumer.processed_contexts_backup (
    id                UUID,
    user_id           VARCHAR(255),
    session_id        VARCHAR(255),
    essence           TEXT,
    intent            VARCHAR(100),
    domains           TEXT[],
    embedding         vector(384),
    embedding_model   VARCHAR(100),
    embedding_version VARCHAR(50),
    message_count     INTEGER,
    platform          VARCHAR(50),
    processed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ
);

COMMENT ON TABLE consumer.processed_contexts_backup IS 'Backup of processed_contexts with 384-dim embeddings (pre-model upgrade)';

CREATE TABLE IF NOT EXISTS consumer.velocity_memories (
    memory_id        TEXT        NOT NULL DEFAULT ('vmem_' || replace(gen_random_uuid()::text, '-', '')),
    user_id          VARCHAR     NOT NULL,
    scope            VARCHAR     NOT NULL DEFAULT 'default',
    content          TEXT        NOT NULL,
    memory_type      VARCHAR     NOT NULL,
    safety_labels    TEXT[]      NOT NULL DEFAULT '{}',
    source           VARCHAR     NOT NULL DEFAULT 'contextengine',
    metadata         JSONB       NOT NULL DEFAULT '{}',
    write_confidence NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ,
    CONSTRAINT consumer_velocity_memories_pkey PRIMARY KEY (memory_id),
    CONSTRAINT consumer_velocity_memories_confidence_check CHECK (write_confidence >= 0 AND write_confidence <= 1)
);

COMMENT ON TABLE consumer.velocity_memories IS 'Provider-neutral durable memory records for ContextEngine.';

CREATE TABLE IF NOT EXISTS consumer.user_profiles (
    user_id         VARCHAR(255) NOT NULL,
    primary_domains JSONB        NOT NULL DEFAULT '[]',
    common_intents  JSONB        NOT NULL DEFAULT '[]',
    recent_essences TEXT[]       NOT NULL DEFAULT '{}',
    stats           JSONB        NOT NULL DEFAULT '{}',
    first_seen      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_active     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT consumer_user_profiles_pkey PRIMARY KEY (user_id)
);

COMMENT ON TABLE consumer.user_profiles IS 'Context engine: aggregated user domain/intent profile';

CREATE TABLE IF NOT EXISTS consumer.user_context (
    id         INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id    INTEGER NOT NULL,
    prompt_id  INTEGER,
    embedding  BYTEA,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_user_context_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_user_context_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

-- =============================================================================
-- REFERRALS & INVITES
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.referrals (
    referral_id              INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id                  INTEGER      NOT NULL,
    referral_code            VARCHAR(255) NOT NULL,
    times_used               INTEGER      DEFAULT 0,
    tokens_received_by_referrer INTEGER   DEFAULT 50,
    tokens_awarded_by_referrer  INTEGER   DEFAULT 30,
    created_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_referrals_pkey PRIMARY KEY (referral_id),
    CONSTRAINT consumer_referrals_code_key UNIQUE (referral_code),
    CONSTRAINT consumer_referrals_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.referral_relations (
    id           INTEGER      NOT NULL DEFAULT nextval('consumer.referral_relations_id_seq'),
    inviter_id   INTEGER      NOT NULL,
    invitee_id   INTEGER      NOT NULL,
    referral_code VARCHAR(100) NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'pending',
    reward_tries INTEGER      NOT NULL DEFAULT 5,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  DEFAULT now(),
    updated_at   TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_referral_relations_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_referral_relations_invitee_key UNIQUE (invitee_id),
    CONSTRAINT consumer_referral_relations_inviter_fkey FOREIGN KEY (inviter_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_referral_relations_invitee_fkey FOREIGN KEY (invitee_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE SEQUENCE IF NOT EXISTS consumer.referral_relations_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE consumer.referral_relations_id_seq OWNED BY consumer.referral_relations.id;

CREATE TABLE IF NOT EXISTS consumer.invite_links (
    id                  INTEGER   NOT NULL GENERATED ALWAYS AS IDENTITY,
    invite_code         VARCHAR(50) NOT NULL,
    generated_by_user_id INTEGER  NOT NULL,
    link_url            TEXT      NOT NULL,
    usage_count         INTEGER   NOT NULL DEFAULT 0,
    emails_sent         TEXT[]    NOT NULL DEFAULT '{}',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_invite_links_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_invite_links_code_key UNIQUE (invite_code),
    CONSTRAINT consumer_invite_links_user_id_fkey FOREIGN KEY (generated_by_user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.invite_redemptions (
    id                   INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    invite_link_id       INTEGER      NOT NULL,
    redeemed_by_user_id  INTEGER,
    redeemed_email       VARCHAR(255) NOT NULL,
    reward_granted       BOOLEAN      NOT NULL DEFAULT FALSE,
    redeemed_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_invite_redemptions_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_invite_redemptions_link_id_fkey FOREIGN KEY (invite_link_id) REFERENCES consumer.invite_links(id) ON DELETE CASCADE,
    CONSTRAINT consumer_invite_redemptions_user_id_fkey FOREIGN KEY (redeemed_by_user_id) REFERENCES shared.users(user_id) ON DELETE SET NULL
);

-- =============================================================================
-- ENGAGEMENT & EMAIL
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.engagement_email_log (
    id             BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id        INTEGER     NOT NULL,
    campaign_type  VARCHAR(100) NOT NULL,
    trigger_source VARCHAR(100),
    metadata       JSONB       NOT NULL DEFAULT '{}',
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_engagement_email_log_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_engagement_email_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.engagement_rewards (
    id            BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id       INTEGER     NOT NULL,
    action        VARCHAR(64) NOT NULL,
    context       VARCHAR(64) NOT NULL,
    tries_granted INTEGER     NOT NULL DEFAULT 5,
    metadata      JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consumer_engagement_rewards_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_engagement_rewards_unique_claim UNIQUE (user_id, action, context),
    CONSTRAINT consumer_engagement_rewards_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.inactive_email_sent (
    user_id    INTEGER     NOT NULL,
    email_type VARCHAR(10) NOT NULL,
    sent_at    TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT consumer_inactive_email_sent_pkey PRIMARY KEY (user_id, email_type),
    CONSTRAINT consumer_inactive_email_sent_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

-- =============================================================================
-- ONBOARDING & PERSONALIZATION
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.onboarding_data (
    id              INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id         INTEGER      NOT NULL,
    llm_platform    VARCHAR(255) NOT NULL,
    occupation      VARCHAR(255) NOT NULL,
    source          VARCHAR(255) NOT NULL,
    problems_faced  VARCHAR(255),
    use_case        VARCHAR(255),
    ai_familiarity  VARCHAR(20)  DEFAULT 'Beginner',
    tries_granted   INTEGER,
    created_at      TIMESTAMPTZ  DEFAULT now(),
    updated_at      TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_onboarding_data_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_onboarding_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_onboarding_data_ai_familiarity_check CHECK (ai_familiarity IN ('Beginner', 'Amateur', 'Intermediate', 'Master', 'Expert'))
);

CREATE TABLE IF NOT EXISTS consumer.user_personalization (
    id                 INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id            INTEGER NOT NULL,
    preferred_name     TEXT,
    professional_world TEXT,
    velocity_traits    TEXT,
    personal_life      TEXT,
    hobbies            TEXT,
    primary_model      VARCHAR(20),
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_user_personalization_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_user_personalization_user_id_key UNIQUE (user_id),
    CONSTRAINT consumer_user_personalization_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE,
    CONSTRAINT consumer_user_personalization_model_check CHECK (primary_model IN ('ChatGPT', 'Claude', 'Gemini'))
);

-- =============================================================================
-- REVIEWS, CONTACT, MISC
-- =============================================================================

CREATE TABLE IF NOT EXISTS consumer.reviews (
    id           INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id      INTEGER      NOT NULL,
    reason       VARCHAR(255) NOT NULL,
    feedback     TEXT,
    image_url    TEXT,
    source       VARCHAR(100) DEFAULT 'other',
    submitted_at TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_reviews_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS consumer.contact_messages (
    message_id INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id    INTEGER,
    name       VARCHAR(150) NOT NULL,
    email      VARCHAR(255) NOT NULL,
    message    TEXT         NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumer_contact_messages_pkey PRIMARY KEY (message_id),
    CONSTRAINT consumer_contact_messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE SET NULL
);

COMMENT ON TABLE consumer.contact_messages IS 'Submissions from the Contact Us form';

CREATE TABLE IF NOT EXISTS consumer.launchlist (
    id         INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    email      VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_launchlist_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_launchlist_email_key UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS consumer.waitlistusers (
    waitlist_id INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    name        VARCHAR(255),
    email       VARCHAR(255) NOT NULL,
    verified    BOOLEAN      DEFAULT FALSE,
    created_at  TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_waitlistusers_pkey PRIMARY KEY (waitlist_id),
    CONSTRAINT consumer_waitlistusers_email_key UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS consumer.api_error_logs (
    id            INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    error_id      VARCHAR(255) NOT NULL DEFAULT gen_random_uuid()::text,
    api_endpoint  VARCHAR(500) NOT NULL,
    api_method    VARCHAR(10),
    error_message TEXT         NOT NULL,
    error_type    VARCHAR(100),
    user_id       INTEGER,
    source        VARCHAR(50),
    created_at    TIMESTAMP    DEFAULT now(),
    CONSTRAINT consumer_api_error_logs_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_api_error_logs_error_id_key UNIQUE (error_id)
);

COMMENT ON TABLE consumer.api_error_logs IS 'API error audit trail. SOC2 PI1.1.';

CREATE TABLE IF NOT EXISTS consumer.suggestion_prompt (
    id         INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    prompt     TEXT         NOT NULL,
    occupation VARCHAR(255),
    created_at TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_suggestion_prompt_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS consumer.free_trial_user_availability (
    email      VARCHAR(255) NOT NULL,
    threshold  INTEGER      DEFAULT 3,
    created_at TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT consumer_free_trial_user_availability_pkey PRIMARY KEY (email)
);

CREATE TABLE IF NOT EXISTS consumer.essence_usage_tracking (
    id               INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY,
    user_id          INTEGER      NOT NULL,
    date             DATE         NOT NULL DEFAULT CURRENT_DATE,
    essence_creations INTEGER     DEFAULT 0,
    api_calls        INTEGER      DEFAULT 0,
    cost_estimate    NUMERIC(10,4) DEFAULT 0,
    created_at       TIMESTAMP    DEFAULT now(),
    updated_at       TIMESTAMP    DEFAULT now(),
    CONSTRAINT consumer_essence_usage_tracking_pkey PRIMARY KEY (id),
    CONSTRAINT consumer_essence_usage_tracking_user_date_key UNIQUE (user_id, date),
    CONSTRAINT consumer_essence_usage_tracking_user_id_fkey FOREIGN KEY (user_id) REFERENCES shared.users(user_id) ON DELETE CASCADE
);

-- =============================================================================
-- VIEWS
-- =============================================================================

CREATE OR REPLACE VIEW consumer.user_token_summary AS
SELECT
    user_id,
    COALESCE(SUM(current_amount) FILTER (WHERE expires_at IS NULL OR expires_at > now()), 0)::INTEGER AS total_available,
    COALESCE(SUM(current_amount) FILTER (WHERE token_type = 'subscription' AND (expires_at IS NULL OR expires_at > now())), 0)::INTEGER AS subscription_tokens,
    COALESCE(SUM(current_amount) FILTER (WHERE token_type = 'purchased'), 0)::INTEGER AS purchased_tokens,
    COALESCE(SUM(current_amount) FILTER (WHERE token_type IN ('referral', 'coupon', 'bonus', 'compensation', 'legacy')), 0)::INTEGER AS bonus_tokens,
    COALESCE(SUM(current_amount) FILTER (WHERE expires_at IS NOT NULL AND expires_at > now() AND expires_at <= now() + INTERVAL '7 days'), 0)::INTEGER AS expiring_soon,
    COALESCE(SUM(initial_amount), 0)::INTEGER AS total_granted,
    COALESCE(SUM(initial_amount - current_amount), 0)::INTEGER AS total_used
FROM consumer.token_ledger
GROUP BY user_id;

COMMENT ON VIEW consumer.user_token_summary IS 'Aggregated token balance by type for quick lookup';

CREATE OR REPLACE VIEW consumer.expiring_tokens_report AS
SELECT
    tl.user_id,
    u.email,
    u.name AS username,
    tl.id AS ledger_id,
    tl.token_type,
    tl.source_reference,
    tl.current_amount,
    tl.expires_at,
    (tl.expires_at - now()) AS time_until_expiry,
    EXTRACT(epoch FROM (tl.expires_at - now())) / 86400 AS days_until_expiry,
    CASE
        WHEN tl.expires_at <= now()                        THEN 'expired'
        WHEN tl.expires_at <= now() + INTERVAL '1 day'    THEN 'expiring_today'
        WHEN tl.expires_at <= now() + INTERVAL '7 days'   THEN 'expiring_this_week'
        WHEN tl.expires_at <= now() + INTERVAL '30 days'  THEN 'expiring_this_month'
        ELSE 'expiring_later'
    END AS expiry_status
FROM consumer.token_ledger tl
LEFT JOIN shared.users u ON tl.user_id = u.user_id
WHERE tl.expires_at IS NOT NULL
  AND tl.current_amount > 0
  AND tl.expires_at > now() - INTERVAL '1 day'
ORDER BY tl.expires_at;

-- =============================================================================
-- FUNCTIONS referencing views
-- =============================================================================

CREATE OR REPLACE FUNCTION consumer.get_user_token_balance(p_user_id INTEGER)
RETURNS TABLE(total_available INTEGER, subscription_tokens INTEGER, purchased_tokens INTEGER, bonus_tokens INTEGER, expiring_soon INTEGER)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        uts.total_available,
        uts.subscription_tokens,
        uts.purchased_tokens,
        uts.bonus_tokens,
        uts.expiring_soon
    FROM consumer.user_token_summary uts
    WHERE uts.user_id = p_user_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 0, 0, 0, 0, 0;
    END IF;
END;
$$;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

CREATE TRIGGER trg_save_enhance_prompt_mode
    BEFORE INSERT OR UPDATE ON consumer.save_enhance_prompt
    FOR EACH ROW EXECUTE FUNCTION consumer.normalize_enhance_mode();

CREATE TRIGGER trg_webhook_events_block_downtime
    BEFORE INSERT ON consumer.webhook_events
    FOR EACH ROW EXECUTE FUNCTION consumer.block_payment_downtime_events();
