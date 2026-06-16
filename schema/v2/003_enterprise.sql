-- =============================================================================
-- 003_enterprise.sql — ThinkVelocity Enterprise Schema
-- Schema: enterprise
-- Purpose: All tables for the enterprise product (enterprise.thinkvelocity.in)
--          Served by: NestJS enterprise backend (:3000)
-- Run order: THIRD (depends on shared schema for cross-schema FKs)
-- Source DB: enterprise (32 tables, PrismaORM-managed)
-- Note: Prisma migration table (_prisma_migrations) excluded — Prisma manages it
-- =============================================================================

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

CREATE TYPE enterprise."DecisionActionType" AS ENUM (
    'ALLOW', 'WARN', 'REDACT', 'BLOCK', 'REQUIRE_CONFIRMATION', 'REQUIRE_APPROVAL'
);

CREATE TYPE enterprise."GuardrailQueueStatus" AS ENUM (
    'PENDING', 'APPROVED', 'REJECTED'
);

CREATE TYPE enterprise."HierarchyType" AS ENUM (
    'TWO_LEVEL', 'THREE_LEVEL'
);

CREATE TYPE enterprise."ModerationContentType" AS ENUM (
    'COMPANY_POLICY', 'PROJECT_POLICY', 'CHAT_PROMPT'
);

CREATE TYPE enterprise."NotificationType" AS ENUM (
    'CONTENT_CREATED', 'CONTENT_UPDATED', 'CONTENT_DELETED'
);

CREATE TYPE enterprise."OnboardingRunStatus" AS ENUM (
    'IN_PROGRESS', 'COMPLETED', 'FAILED'
);

CREATE TYPE enterprise."OnboardingStatus" AS ENUM (
    'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED'
);

-- Additional enums (from full dump — add per actual pg_dump output)
-- CREATE TYPE enterprise."RoleType" AS ENUM (...);
-- CREATE TYPE enterprise."PermissionType" AS ENUM (...);

-- =============================================================================
-- CORE ENTERPRISE ENTITIES
-- Note: Enterprise has its own User table (NestJS/Prisma managed)
--       enterprise.User.id is a cuid/uuid string, NOT linked to shared.users
--       (Enterprise auth is separate from consumer auth)
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprise."Enterprise" (
    id          TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    domain      TEXT,
    "hierarchyType" enterprise."HierarchyType" NOT NULL DEFAULT 'TWO_LEVEL',
    "onboardingStatus" enterprise."OnboardingStatus" NOT NULL DEFAULT 'NOT_STARTED',
    "createdAt"  TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS enterprise."User" (
    id              TEXT        NOT NULL,
    email           TEXT        NOT NULL,
    name            TEXT,
    password        TEXT,
    "enterpriseId"  TEXT        NOT NULL,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_user_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_user_email_key UNIQUE (email),
    CONSTRAINT enterprise_user_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."Role" (
    id              TEXT NOT NULL,
    name            TEXT NOT NULL,
    "enterpriseId"  TEXT NOT NULL,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_role_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_role_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."Permission" (
    id          TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_permission_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_permission_name_key UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS enterprise."RolePermission" (
    "roleId"       TEXT NOT NULL,
    "permissionId" TEXT NOT NULL,
    CONSTRAINT enterprise_role_permission_pkey PRIMARY KEY ("roleId", "permissionId"),
    CONSTRAINT enterprise_role_permission_role_fkey FOREIGN KEY ("roleId") REFERENCES enterprise."Role"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_role_permission_permission_fkey FOREIGN KEY ("permissionId") REFERENCES enterprise."Permission"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."UserRole" (
    "userId" TEXT NOT NULL,
    "roleId" TEXT NOT NULL,
    CONSTRAINT enterprise_user_role_pkey PRIMARY KEY ("userId", "roleId"),
    CONSTRAINT enterprise_user_role_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_user_role_role_fkey FOREIGN KEY ("roleId") REFERENCES enterprise."Role"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."Team" (
    id              TEXT NOT NULL,
    name            TEXT NOT NULL,
    "enterpriseId"  TEXT NOT NULL,
    "parentTeamId"  TEXT,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_team_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_team_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_team_parent_fkey FOREIGN KEY ("parentTeamId") REFERENCES enterprise."Team"(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS enterprise."TeamUser" (
    "teamId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    CONSTRAINT enterprise_team_user_pkey PRIMARY KEY ("teamId", "userId"),
    CONSTRAINT enterprise_team_user_team_fkey FOREIGN KEY ("teamId") REFERENCES enterprise."Team"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_team_user_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE
);

-- =============================================================================
-- CONTENT & PROMPTS
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprise."Content" (
    id              TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    body            TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "teamId"        TEXT,
    "createdById"   TEXT    NOT NULL,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_content_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_content_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_content_team_fkey FOREIGN KEY ("teamId") REFERENCES enterprise."Team"(id) ON DELETE SET NULL,
    CONSTRAINT enterprise_content_user_fkey FOREIGN KEY ("createdById") REFERENCES enterprise."User"(id)
);

CREATE TABLE IF NOT EXISTS enterprise."ContentTeam" (
    "contentId" TEXT NOT NULL,
    "teamId"    TEXT NOT NULL,
    CONSTRAINT enterprise_content_team_pkey PRIMARY KEY ("contentId", "teamId"),
    CONSTRAINT enterprise_content_team_content_fkey FOREIGN KEY ("contentId") REFERENCES enterprise."Content"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_content_team_team_fkey FOREIGN KEY ("teamId") REFERENCES enterprise."Team"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."UserPrompt" (
    id              TEXT    NOT NULL,
    "userId"        TEXT    NOT NULL,
    prompt          TEXT    NOT NULL,
    platform        TEXT,
    "enterpriseId"  TEXT    NOT NULL,
    "teamId"        TEXT,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_user_prompt_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_user_prompt_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_user_prompt_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."EnhancedPrompt" (
    id                  TEXT    NOT NULL,
    "userPromptId"      TEXT    NOT NULL,
    "enhancedPrompt"    TEXT    NOT NULL,
    "processingTime"    NUMERIC,
    intent              TEXT,
    llm                 TEXT,
    complexity          TEXT,
    domain              TEXT,
    mode                TEXT,
    "inputToken"        INTEGER,
    "outputToken"       INTEGER,
    "totalToken"        INTEGER,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_enhanced_prompt_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_enhanced_prompt_user_prompt_fkey FOREIGN KEY ("userPromptId") REFERENCES enterprise."UserPrompt"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."RefinePrompt" (
    id                  TEXT    NOT NULL,
    "enhancedPromptId"  TEXT    NOT NULL,
    "refinedPrompt"     TEXT    NOT NULL,
    "processingTime"    NUMERIC,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_refine_prompt_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_refine_prompt_enhanced_fkey FOREIGN KEY ("enhancedPromptId") REFERENCES enterprise."EnhancedPrompt"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."RefinePromptLegacy" (
    id                  TEXT    NOT NULL,
    "userId"            TEXT    NOT NULL,
    "enhancedPromptId"  TEXT,
    "refinedPrompt"     TEXT    NOT NULL,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_refine_prompt_legacy_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS enterprise."SaveEnhancePrompt" (
    id                  TEXT    NOT NULL,
    "userId"            TEXT    NOT NULL,
    "enhancedPromptId"  TEXT    NOT NULL,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_save_enhance_prompt_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_save_enhance_prompt_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_save_enhance_prompt_enhanced_fkey FOREIGN KEY ("enhancedPromptId") REFERENCES enterprise."EnhancedPrompt"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."Conversation" (
    id              TEXT    NOT NULL,
    "userId"        TEXT    NOT NULL,
    title           TEXT,
    "enterpriseId"  TEXT    NOT NULL,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_conversation_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_conversation_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_conversation_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."prompt_collections" (
    id          TEXT NOT NULL,
    "userId"    TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_prompt_collections_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_prompt_collections_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."collection_prompts" (
    id                  TEXT NOT NULL,
    "collectionId"      TEXT NOT NULL,
    "enhancedPromptId"  TEXT NOT NULL,
    "createdAt"         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_collection_prompts_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_collection_prompts_collection_fkey FOREIGN KEY ("collectionId") REFERENCES enterprise."prompt_collections"(id) ON DELETE CASCADE
);

-- =============================================================================
-- COMPANY POLICY & GUARDRAILS
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprise."CompanyPolicy" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    description     TEXT,
    content         TEXT    NOT NULL,
    "isActive"      BOOLEAN NOT NULL DEFAULT TRUE,
    "createdById"   TEXT,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_company_policy_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_company_policy_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."company_policy_history" (
    id          TEXT    NOT NULL,
    "policyId"  TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    "changedAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    "changedBy" TEXT,
    CONSTRAINT enterprise_company_policy_history_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_company_policy_history_policy_fkey FOREIGN KEY ("policyId") REFERENCES enterprise."CompanyPolicy"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."ModerationLog" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "userId"        TEXT,
    "contentType"   enterprise."ModerationContentType" NOT NULL,
    "contentId"     TEXT,
    decision        enterprise."DecisionActionType" NOT NULL,
    reason          TEXT,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_moderation_log_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_moderation_log_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."moderation_audit_log" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "userId"        TEXT,
    action          TEXT    NOT NULL,
    details         JSONB   DEFAULT '{}',
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_moderation_audit_log_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS enterprise."content_policy_results" (
    id              TEXT    NOT NULL,
    "contentId"     TEXT,
    "policyId"      TEXT    NOT NULL,
    passed          BOOLEAN NOT NULL,
    violations      JSONB   DEFAULT '[]',
    "checkedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_content_policy_results_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_content_policy_results_policy_fkey FOREIGN KEY ("policyId") REFERENCES enterprise."CompanyPolicy"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."prompt_moderation_results" (
    id              TEXT    NOT NULL,
    "promptId"      TEXT    NOT NULL,
    "policyId"      TEXT    NOT NULL,
    passed          BOOLEAN NOT NULL,
    violations      JSONB   DEFAULT '[]',
    decision        enterprise."DecisionActionType",
    "checkedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_prompt_moderation_results_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_prompt_moderation_results_policy_fkey FOREIGN KEY ("policyId") REFERENCES enterprise."CompanyPolicy"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."guardrail_approval_queue" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "userId"        TEXT    NOT NULL,
    "promptId"      TEXT,
    "policyId"      TEXT    NOT NULL,
    status          enterprise."GuardrailQueueStatus" NOT NULL DEFAULT 'PENDING',
    "reviewedBy"    TEXT,
    "reviewedAt"    TIMESTAMPTZ,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_guardrail_approval_queue_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_guardrail_approval_queue_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE,
    CONSTRAINT enterprise_guardrail_approval_queue_policy_fkey FOREIGN KEY ("policyId") REFERENCES enterprise."CompanyPolicy"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."rule_toggle_state" (
    id          TEXT    NOT NULL,
    "ruleId"    TEXT    NOT NULL,
    "isEnabled" BOOLEAN NOT NULL DEFAULT TRUE,
    "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_rule_toggle_state_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_rule_toggle_state_rule_key UNIQUE ("ruleId")
);

-- =============================================================================
-- NOTIFICATIONS & ONBOARDING
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprise."Notification" (
    id          TEXT    NOT NULL,
    "userId"    TEXT    NOT NULL,
    type        enterprise."NotificationType" NOT NULL,
    title       TEXT    NOT NULL,
    body        TEXT,
    read        BOOLEAN NOT NULL DEFAULT FALSE,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_notification_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_notification_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."onboarding_runs" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "runBy"         TEXT    NOT NULL,
    status          enterprise."OnboardingRunStatus" NOT NULL DEFAULT 'IN_PROGRESS',
    "startedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "completedAt"   TIMESTAMPTZ,
    error           TEXT,
    metadata        JSONB   DEFAULT '{}',
    CONSTRAINT enterprise_onboarding_runs_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_onboarding_runs_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

-- =============================================================================
-- AUDIT & REVIEWS
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprise."AuditLog" (
    id              TEXT    NOT NULL,
    "enterpriseId"  TEXT    NOT NULL,
    "userId"        TEXT,
    action          TEXT    NOT NULL,
    resource        TEXT,
    "resourceId"    TEXT,
    details         JSONB   DEFAULT '{}',
    "ipAddress"     TEXT,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_audit_log_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_audit_log_enterprise_fkey FOREIGN KEY ("enterpriseId") REFERENCES enterprise."Enterprise"(id) ON DELETE CASCADE
);

COMMENT ON TABLE enterprise."AuditLog" IS 'Enterprise action audit trail. SOC2 PI1.1, CC7.2.';

CREATE TABLE IF NOT EXISTS enterprise."UserPersonalization" (
    id              TEXT    NOT NULL,
    "userId"        TEXT    NOT NULL,
    preferences     JSONB   DEFAULT '{}',
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_user_personalization_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_user_personalization_user_key UNIQUE ("userId"),
    CONSTRAINT enterprise_user_personalization_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS enterprise."reviews" (
    id          TEXT    NOT NULL,
    "userId"    TEXT    NOT NULL,
    rating      INTEGER,
    feedback    TEXT,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT enterprise_reviews_pkey PRIMARY KEY (id),
    CONSTRAINT enterprise_reviews_user_fkey FOREIGN KEY ("userId") REFERENCES enterprise."User"(id) ON DELETE CASCADE
);
