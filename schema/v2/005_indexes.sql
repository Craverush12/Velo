-- =============================================================================
-- 005_indexes.sql — ThinkVelocity Consolidated Schema — Indexes
-- Purpose: All composite and single-column indexes for query performance.
--          Derived from: actual EXPLAIN ANALYZE on production queries + pg_stat_user_indexes
-- Run order: FIFTH (all tables must exist)
-- SOC2: Indirectly supports A1.2 (backup speed) and CC7.2 (availability/latency)
-- =============================================================================

-- =============================================================================
-- SHARED SCHEMA INDEXES
-- =============================================================================

-- Auth: refresh token lookups by user (token revocation, session listing)
CREATE INDEX IF NOT EXISTS idx_shared_refresh_tokens_user_id
    ON shared.refresh_tokens (user_id);

-- Auth: token lookup by hash (login validation)
CREATE INDEX IF NOT EXISTS idx_shared_refresh_tokens_token_hash
    ON shared.refresh_tokens (token_hash)
    WHERE revoked = FALSE;

-- Auth: cleanup expired tokens
CREATE INDEX IF NOT EXISTS idx_shared_refresh_tokens_expires_at
    ON shared.refresh_tokens (expires_at)
    WHERE revoked = FALSE;

-- OTP: lookup by email+otp (verification flow)
CREATE INDEX IF NOT EXISTS idx_shared_otp_verification_email
    ON shared.otp_verification (email, created_at DESC);

-- Users: email lookup (login)
CREATE INDEX IF NOT EXISTS idx_shared_users_email
    ON shared.users (email);

-- Users: google_id lookup (OAuth)
CREATE INDEX IF NOT EXISTS idx_shared_users_google_id
    ON shared.users (google_id)
    WHERE google_id IS NOT NULL;

-- =============================================================================
-- CONSUMER SCHEMA INDEXES
-- =============================================================================

-- ---------- Prompt tables ----------

-- user_prompts: list prompts by user (history page)
CREATE INDEX IF NOT EXISTS idx_consumer_user_prompts_user_id
    ON consumer.user_prompts (user_id, created_at DESC);

-- save_enhance_prompt: lookup by user (dashboard)
CREATE INDEX IF NOT EXISTS idx_consumer_save_enhance_user_id
    ON consumer.save_enhance_prompt (user_id, created_at DESC);

-- save_enhance_prompt: lookup by prompt_id (refine flow)
CREATE INDEX IF NOT EXISTS idx_consumer_save_enhance_prompt_id
    ON consumer.save_enhance_prompt (prompt_id);

-- refine_prompt: lookup by enhanced_prompt_id
CREATE INDEX IF NOT EXISTS idx_consumer_refine_enhanced_prompt_id
    ON consumer.refine_prompt (enhanced_prompt_id);

-- refine_prompt: lookup by user_id
CREATE INDEX IF NOT EXISTS idx_consumer_refine_user_id
    ON consumer.refine_prompt (user_id, created_at DESC);

-- prompt_history: user history
CREATE INDEX IF NOT EXISTS idx_consumer_prompt_history_user_id
    ON consumer.prompt_history (user_id, created_at DESC);

-- ---------- Conversations ----------

-- conversations: user's conversations
CREATE INDEX IF NOT EXISTS idx_consumer_conversations_user_id
    ON consumer.conversations (user_id, last_message_at DESC)
    WHERE is_deleted = FALSE;

-- conversation_messages: messages in a conversation
CREATE INDEX IF NOT EXISTS idx_consumer_conversation_messages_conv_id
    ON consumer.conversation_messages (conversation_id, created_at ASC)
    WHERE is_deleted = FALSE;

-- ---------- Context Engine ----------

-- conversation_contexts: user's contexts (most recent first)
CREATE INDEX IF NOT EXISTS idx_consumer_conv_contexts_user_id
    ON consumer.conversation_contexts (user_id, created_at DESC);

-- conversation_contexts: session lookup (context engine dedup)
CREATE INDEX IF NOT EXISTS idx_consumer_conv_contexts_session
    ON consumer.conversation_contexts (user_id, session_id);

-- processed_contexts: user's processed contexts
CREATE INDEX IF NOT EXISTS idx_consumer_processed_contexts_user_id
    ON consumer.processed_contexts (user_id, processed_at DESC);

-- processed_contexts: vector similarity search (pgvector IVFFlat)
-- Note: Requires at least 1000 rows for meaningful performance
-- Run: SET ivfflat.probes = 10; before similarity queries
CREATE INDEX IF NOT EXISTS idx_consumer_processed_contexts_embedding
    ON consumer.processed_contexts
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- velocity_memories: user memories by scope
CREATE INDEX IF NOT EXISTS idx_consumer_velocity_memories_user_scope
    ON consumer.velocity_memories (user_id, scope, created_at DESC)
    WHERE deleted_at IS NULL;

-- velocity_memories: expiry cleanup
CREATE INDEX IF NOT EXISTS idx_consumer_velocity_memories_expires_at
    ON consumer.velocity_memories (expires_at)
    WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

-- ---------- Collections ----------

-- prompt_collections: user's collections
CREATE INDEX IF NOT EXISTS idx_consumer_prompt_collections_user_id
    ON consumer.prompt_collections (user_id, created_at DESC);

-- collection_prompts: prompts in a collection
CREATE INDEX IF NOT EXISTS idx_consumer_collection_prompts_collection_id
    ON consumer.collection_prompts (collection_id);

-- ---------- Marketplace ----------

-- prompt_marketplace: non-deleted active prompts
CREATE INDEX IF NOT EXISTS idx_consumer_marketplace_active
    ON consumer.prompt_marketplace (created_at DESC)
    WHERE is_deleted = FALSE;

-- prompt_marketplace: by domain/intent (browse/filter)
CREATE INDEX IF NOT EXISTS idx_consumer_marketplace_domain_intent
    ON consumer.prompt_marketplace (domain, intent)
    WHERE is_deleted = FALSE;

-- prompt_memory: user's saved marketplace prompts
CREATE INDEX IF NOT EXISTS idx_consumer_prompt_memory_user_id
    ON consumer.prompt_memory (user_id, created_at DESC);

-- ---------- Token Economy ----------

-- token_ledger: user's ledger (balance lookup)
CREATE INDEX IF NOT EXISTS idx_consumer_token_ledger_user_id
    ON consumer.token_ledger (user_id, created_at DESC);

-- token_ledger: active non-expired tokens (balance calc)
CREATE INDEX IF NOT EXISTS idx_consumer_token_ledger_user_active
    ON consumer.token_ledger (user_id)
    WHERE current_amount > 0 AND (expires_at IS NULL OR expires_at > now());

-- token_ledger: expiry cleanup job
CREATE INDEX IF NOT EXISTS idx_consumer_token_ledger_expires_at
    ON consumer.token_ledger (expires_at)
    WHERE expires_at IS NOT NULL AND current_amount > 0;

-- token_transactions: audit trail by user
CREATE INDEX IF NOT EXISTS idx_consumer_token_transactions_user_id
    ON consumer.token_transactions (user_id, created_at DESC);

-- token_transactions: idempotency lookup
CREATE INDEX IF NOT EXISTS idx_consumer_token_transactions_idempotency
    ON consumer.token_transactions (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- token_reservations: pending reservations by user (concurrent safety)
CREATE INDEX IF NOT EXISTS idx_consumer_token_reservations_user_pending
    ON consumer.token_reservations (user_id, expires_at)
    WHERE status = 'pending';

-- ---------- Subscriptions & Payments ----------

-- subscriptions: user's active subscription
CREATE INDEX IF NOT EXISTS idx_consumer_subscriptions_user_id
    ON consumer.subscriptions (user_id, status);

-- subscriptions: active subscriptions (billing job)
CREATE INDEX IF NOT EXISTS idx_consumer_subscriptions_active
    ON consumer.subscriptions (current_period_end)
    WHERE status IN ('active', 'past_due');

-- payments: user's payment history
CREATE INDEX IF NOT EXISTS idx_consumer_payments_user_id
    ON consumer.payments (user_id, created_at DESC);

-- webhook_events: unprocessed events (worker pickup)
CREATE INDEX IF NOT EXISTS idx_consumer_webhook_events_unprocessed
    ON consumer.webhook_events (created_at ASC)
    WHERE status = 'received';

-- ---------- Referrals & Invites ----------

-- referrals: lookup by referral_code (signup flow)
CREATE INDEX IF NOT EXISTS idx_consumer_referrals_code
    ON consumer.referrals (referral_code);

-- referrals: lookup by user
CREATE INDEX IF NOT EXISTS idx_consumer_referrals_user_id
    ON consumer.referrals (user_id);

-- referral_relations: inviter's referrals
CREATE INDEX IF NOT EXISTS idx_consumer_referral_relations_inviter
    ON consumer.referral_relations (inviter_id, created_at DESC);

-- ---------- Engagement ----------

-- engagement_email_log: user's campaign history
CREATE INDEX IF NOT EXISTS idx_consumer_engagement_email_log_user
    ON consumer.engagement_email_log (user_id, campaign_type, sent_at DESC);

-- engagement_rewards: lookup by user+action (idempotency)
CREATE INDEX IF NOT EXISTS idx_consumer_engagement_rewards_user_action
    ON consumer.engagement_rewards (user_id, action, context);

-- ---------- Error Logging (SOC2 PI1.1) ----------

-- api_error_logs: recent errors (alerting)
CREATE INDEX IF NOT EXISTS idx_consumer_api_error_logs_created_at
    ON consumer.api_error_logs (created_at DESC);

-- api_error_logs: errors by endpoint (debugging)
CREATE INDEX IF NOT EXISTS idx_consumer_api_error_logs_endpoint
    ON consumer.api_error_logs (api_endpoint, created_at DESC);

-- ---------- Essence / Context Usage ----------

-- essence_usage_tracking: user+date (daily upsert)
CREATE INDEX IF NOT EXISTS idx_consumer_essence_usage_user_date
    ON consumer.essence_usage_tracking (user_id, date DESC);

-- =============================================================================
-- ENTERPRISE SCHEMA INDEXES
-- =============================================================================

-- Enterprise users by enterprise
CREATE INDEX IF NOT EXISTS idx_enterprise_user_enterprise_id
    ON enterprise."User" ("enterpriseId");

-- AuditLog: enterprise + recent (SOC2 evidence)
CREATE INDEX IF NOT EXISTS idx_enterprise_audit_log_enterprise_id
    ON enterprise."AuditLog" ("enterpriseId", "createdAt" DESC);

-- AuditLog: by user
CREATE INDEX IF NOT EXISTS idx_enterprise_audit_log_user_id
    ON enterprise."AuditLog" ("userId", "createdAt" DESC)
    WHERE "userId" IS NOT NULL;

-- ModerationLog: enterprise + recent
CREATE INDEX IF NOT EXISTS idx_enterprise_moderation_log_enterprise_id
    ON enterprise."ModerationLog" ("enterpriseId", "createdAt" DESC);

-- Content: enterprise's content
CREATE INDEX IF NOT EXISTS idx_enterprise_content_enterprise_id
    ON enterprise."Content" ("enterpriseId", "createdAt" DESC);

-- guardrail_approval_queue: pending items
CREATE INDEX IF NOT EXISTS idx_enterprise_guardrail_pending
    ON enterprise."guardrail_approval_queue" ("enterpriseId", status, "createdAt" ASC)
    WHERE status = 'PENDING';

-- UserPrompt: user's prompts
CREATE INDEX IF NOT EXISTS idx_enterprise_user_prompt_user_id
    ON enterprise."UserPrompt" ("userId", "createdAt" DESC);

-- Notification: unread notifications by user
CREATE INDEX IF NOT EXISTS idx_enterprise_notification_user_unread
    ON enterprise."Notification" ("userId", "createdAt" DESC)
    WHERE read = FALSE;

-- =============================================================================
-- EXTENSION SCHEMA INDEXES
-- =============================================================================

-- install_events: user's events
CREATE INDEX IF NOT EXISTS idx_extension_install_events_user_id
    ON extension.install_events (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- feature_usage: user's usage by feature
CREATE INDEX IF NOT EXISTS idx_extension_feature_usage_user_feature
    ON extension.feature_usage (user_id, feature, created_at DESC);

-- api_sessions: active sessions by user
CREATE INDEX IF NOT EXISTS idx_extension_api_sessions_user_id
    ON extension.api_sessions (user_id, last_ping_at DESC)
    WHERE ended_at IS NULL;
