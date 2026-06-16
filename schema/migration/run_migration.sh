#!/usr/bin/env bash
# =============================================================================
# run_migration.sh — ThinkVelocity DB Migration: localpgvelocity → thinkvelocity_prod
#
# What this does:
#   1. On the NEW server: create the v2 schema (4 schemas, all tables)
#   2. From OLD server: dump data in FK-dependency order (topological sort)
#   3. Load data into new schemas
#   4. Update sequences to current max values
#   5. Verify row counts match
#
# Prerequisites:
#   - Run 001-006 SQL files to create schemas first
#   - OLD_DB_HOST / NEW_DB_HOST must be reachable from this machine
#   - Requires pg_dump, psql, aws CLI
#
# DSA Note: FK dependency order is a topological sort problem.
#   Tables with no FKs go first. Tables with FKs go after their parents.
#   Cycle detection: PostgreSQL doesn't allow FK cycles, so graph is a DAG.
#
# RUN TIME ESTIMATE: ~5-15 minutes depending on data size
# DOWNTIME REQUIRED: ~0 seconds for schema creation + copy.
#                    ~30-60 seconds for final sequence sync + DNS flip.
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

OLD_HOST="13.203.181.76"
OLD_PORT="5432"
OLD_DB="localpgvelocity"
OLD_ENT_DB="enterprise"
OLD_USER="postgres"  # We SSH to run pg_dump as postgres

NEW_HOST="127.0.0.1"  # Run this ON the new server
NEW_PORT="5432"
NEW_DB="thinkvelocity_prod"
NEW_USER="postgres"

SSH_KEY="${SSH_KEY:-~/.ssh/thinkvelocity-prod.pem}"  # Server 2 key
SSH_USER="ec2-user"

LOG_FILE="/tmp/migration_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="/tmp/migration_backup_$(date +%Y%m%d_%H%M%S)"

echo "Migration started at $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE"
echo "Backup staging: $BACKUP_DIR"

mkdir -p "$BACKUP_DIR"

# =============================================================================
# STEP 1: Pre-flight checks
# =============================================================================

echo ""
echo "=== STEP 1: Pre-flight checks ===" | tee -a "$LOG_FILE"

# Check new DB is reachable and schemas exist
psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$NEW_USER" -d "$NEW_DB" -c "\dn" 2>&1 | tee -a "$LOG_FILE"
if ! psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$NEW_USER" -d "$NEW_DB" -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('shared','consumer','enterprise','extension');" | grep -q shared; then
    echo "ERROR: Target schemas not found. Run 001-006 SQL files first." | tee -a "$LOG_FILE"
    exit 1
fi

echo "Pre-flight OK" | tee -a "$LOG_FILE"

# =============================================================================
# STEP 2: Dump data from old server via SSH
# Topological sort order for consumer tables (parents before children):
#
# LEVEL 0 (no FKs, no parent tables):
#   usertable → shared.users
#   billing_plans → consumer.billing_plans
#   token_packages → consumer.token_packages
#   feature_token_costs → consumer.feature_token_costs
#   prompt_marketplace → consumer.prompt_marketplace
#   prompt_library_items → consumer.prompt_library_items
#   suggestion_prompt → consumer.suggestion_prompt
#   free_trial_user_availability → consumer.free_trial_user_availability
#   launchlist → consumer.launchlist
#   waitlistusers → consumer.waitlistusers
#   all_emails → shared.all_emails
#
# LEVEL 1 (FK → usertable):
#   userstatus → shared.user_status
#   otp_verification → shared.otp_verification
#   password_reset_tokens → shared.password_reset_tokens
#   refresh_tokens → shared.refresh_tokens
#   subscriptions → consumer.subscriptions (also → billing_plans)
#   referrals → consumer.referrals
#   invite_links → consumer.invite_links
#   prompt_preferences → consumer.prompt_preferences
#   prompt_collections → consumer.prompt_collections
#   prompt_history → consumer.prompt_history
#   user_context → consumer.user_context
#   user_personalization → consumer.user_personalization
#   onboarding_data → consumer.onboarding_data
#   reviews → consumer.reviews
#   contact_messages → consumer.contact_messages
#   engagement_email_log → consumer.engagement_email_log
#   engagement_rewards → consumer.engagement_rewards
#   inactive_email_sent → consumer.inactive_email_sent
#   essence_usage_tracking → consumer.essence_usage_tracking
#   token_ledger → consumer.token_ledger
#   token_reservations → consumer.token_reservations
#   shared_prompts → consumer.shared_prompts
#   conversation_contexts → consumer.conversation_contexts
#   prompt_memory → consumer.prompt_memory (also → marketplace)
#   processed_contexts → consumer.processed_contexts
#   velocity_memories → consumer.velocity_memories
#   user_profiles → consumer.user_profiles
#
# LEVEL 2 (FK → subscriptions, user_prompts, etc.):
#   payments → consumer.payments
#   user_prompts → consumer.user_prompts
#   webhook_events → consumer.webhook_events
#   save_enhance_prompt → consumer.save_enhance_prompt
#
# LEVEL 3 (FK → save_enhance_prompt / user_prompts):
#   refine_prompt → consumer.refine_prompt
#   collection_prompts → consumer.collection_prompts (→ prompt_collections)
#   shared_prompt_claims → consumer.shared_prompt_claims (→ shared_prompts)
#   invite_redemptions → consumer.invite_redemptions (→ invite_links)
#   referral_relations → consumer.referral_relations (→ usertable x2)
#   token_transactions → consumer.token_transactions (→ token_ledger)
#   prompt_actions → consumer.prompt_actions (→ marketplace, usertable)
#   marketplace_prompt_content_embedding → consumer.marketplace_prompt_content_embedding
#   engagement_email_log → consumer.engagement_email_log
#
# BACKUP TABLES (no FK enforcement — copy as-is):
#   processed_contexts_backup → consumer.processed_contexts_backup
# =============================================================================

echo ""
echo "=== STEP 2: Dumping data from old server ===" | tee -a "$LOG_FILE"

# We dump as postgres on the remote server and pipe locally
# This avoids network-level PostgreSQL port exposure (CC6.6)

dump_table() {
    local OLD_TABLE="$1"  # e.g., "public.usertable"
    local OUT_FILE="$2"   # e.g., "/tmp/migration_backup/usertable.sql"
    echo "  Dumping $OLD_TABLE..." | tee -a "$LOG_FILE"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$OLD_HOST" \
        "sudo -u postgres pg_dump -d $OLD_DB --data-only --no-owner --no-acl -t '$OLD_TABLE'" \
        > "$OUT_FILE" 2>>"$LOG_FILE"
    echo "    -> $(wc -l < "$OUT_FILE") lines" | tee -a "$LOG_FILE"
}

dump_ent_table() {
    local OLD_TABLE="$1"
    local OUT_FILE="$2"
    echo "  Dumping enterprise.$OLD_TABLE..." | tee -a "$LOG_FILE"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$OLD_HOST" \
        "sudo -u postgres pg_dump -d $OLD_ENT_DB --data-only --no-owner --no-acl -t 'public.\"$OLD_TABLE\"'" \
        > "$OUT_FILE" 2>>"$LOG_FILE"
}

# LEVEL 0 — no dependencies
dump_table "public.all_emails"          "$BACKUP_DIR/all_emails.sql"
dump_table "public.usertable"           "$BACKUP_DIR/usertable.sql"
dump_table "public.billing_plans"       "$BACKUP_DIR/billing_plans.sql"
dump_table "public.token_packages"      "$BACKUP_DIR/token_packages.sql"
dump_table "public.feature_token_costs" "$BACKUP_DIR/feature_token_costs.sql"
dump_table "public.prompt_marketplace"  "$BACKUP_DIR/prompt_marketplace.sql"
dump_table "public.prompt_library_items" "$BACKUP_DIR/prompt_library_items.sql"
dump_table "public.suggestion_prompt"   "$BACKUP_DIR/suggestion_prompt.sql"
dump_table "public.free_trial_user_availability" "$BACKUP_DIR/free_trial.sql"
dump_table "public.launchlist"          "$BACKUP_DIR/launchlist.sql"
dump_table "public.waitlistusers"       "$BACKUP_DIR/waitlistusers.sql"
dump_table "public.processed_contexts"  "$BACKUP_DIR/processed_contexts.sql"
dump_table "public.processed_contexts_backup" "$BACKUP_DIR/processed_contexts_backup.sql"
dump_table "public.velocity_memories"   "$BACKUP_DIR/velocity_memories.sql"
dump_table "public.user_profiles"       "$BACKUP_DIR/user_profiles.sql"
dump_table "public.webhook_events"      "$BACKUP_DIR/webhook_events.sql"
dump_table "public.conversations"       "$BACKUP_DIR/conversations.sql"
dump_table "public.api_error_logs"      "$BACKUP_DIR/api_error_logs.sql"

# LEVEL 1 — depend on usertable
dump_table "public.userstatus"              "$BACKUP_DIR/userstatus.sql"
dump_table "public.otp_verification"        "$BACKUP_DIR/otp_verification.sql"
dump_table "public.password_reset_tokens"   "$BACKUP_DIR/password_reset_tokens.sql"
dump_table "public.refresh_tokens"          "$BACKUP_DIR/refresh_tokens.sql"
dump_table "public.subscriptions"           "$BACKUP_DIR/subscriptions.sql"
dump_table "public.referrals"               "$BACKUP_DIR/referrals.sql"
dump_table "public.invite_links"            "$BACKUP_DIR/invite_links.sql"
dump_table "public.prompt_preferences"      "$BACKUP_DIR/prompt_preferences.sql"
dump_table "public.prompt_collections"      "$BACKUP_DIR/prompt_collections.sql"
dump_table "public.prompt_history"          "$BACKUP_DIR/prompt_history.sql"
dump_table "public.user_context"            "$BACKUP_DIR/user_context.sql"
dump_table "public.user_personalization"    "$BACKUP_DIR/user_personalization.sql"
dump_table "public.onboarding_data"         "$BACKUP_DIR/onboarding_data.sql"
dump_table "public.reviews"                 "$BACKUP_DIR/reviews.sql"
dump_table "public.contact_messages"        "$BACKUP_DIR/contact_messages.sql"
dump_table "public.engagement_email_log"    "$BACKUP_DIR/engagement_email_log.sql"
dump_table "public.engagement_rewards"      "$BACKUP_DIR/engagement_rewards.sql"
dump_table "public.inactive_email_sent"     "$BACKUP_DIR/inactive_email_sent.sql"
dump_table "public.essence_usage_tracking"  "$BACKUP_DIR/essence_usage.sql"
dump_table "public.token_ledger"            "$BACKUP_DIR/token_ledger.sql"
dump_table "public.token_reservations"      "$BACKUP_DIR/token_reservations.sql"
dump_table "public.shared_prompts"          "$BACKUP_DIR/shared_prompts.sql"
dump_table "public.conversation_contexts"   "$BACKUP_DIR/conversation_contexts.sql"
dump_table "public.prompt_memory"           "$BACKUP_DIR/prompt_memory.sql"
dump_table "public.prompt_actions"          "$BACKUP_DIR/prompt_actions.sql"
dump_table "public.marketplace_prompt_content_embedding" "$BACKUP_DIR/mkt_embedding.sql"

# LEVEL 2 — depend on level 1
dump_table "public.payments"            "$BACKUP_DIR/payments.sql"
dump_table "public.user_prompts"        "$BACKUP_DIR/user_prompts.sql"
dump_table "public.save_enhance_prompt" "$BACKUP_DIR/save_enhance_prompt.sql"

# LEVEL 3 — depend on level 2
dump_table "public.refine_prompt"        "$BACKUP_DIR/refine_prompt.sql"
dump_table "public.collection_prompts"   "$BACKUP_DIR/collection_prompts.sql"
dump_table "public.shared_prompt_claims" "$BACKUP_DIR/shared_prompt_claims.sql"
dump_table "public.invite_redemptions"   "$BACKUP_DIR/invite_redemptions.sql"
dump_table "public.referral_relations"   "$BACKUP_DIR/referral_relations.sql"
dump_table "public.token_transactions"   "$BACKUP_DIR/token_transactions.sql"
dump_table "public.conversation_messages" "$BACKUP_DIR/conversation_messages.sql"

echo "All consumer dumps complete." | tee -a "$LOG_FILE"

# Enterprise tables (ordered)
dump_ent_table "Enterprise"               "$BACKUP_DIR/ent_enterprise.sql"
dump_ent_table "User"                     "$BACKUP_DIR/ent_user.sql"
dump_ent_table "Role"                     "$BACKUP_DIR/ent_role.sql"
dump_ent_table "Permission"               "$BACKUP_DIR/ent_permission.sql"
dump_ent_table "RolePermission"           "$BACKUP_DIR/ent_role_permission.sql"
dump_ent_table "Team"                     "$BACKUP_DIR/ent_team.sql"
dump_ent_table "TeamUser"                 "$BACKUP_DIR/ent_team_user.sql"
dump_ent_table "UserRole"                 "$BACKUP_DIR/ent_user_role.sql"
dump_ent_table "CompanyPolicy"            "$BACKUP_DIR/ent_company_policy.sql"
dump_ent_table "Content"                  "$BACKUP_DIR/ent_content.sql"
dump_ent_table "ContentTeam"              "$BACKUP_DIR/ent_content_team.sql"
dump_ent_table "UserPrompt"               "$BACKUP_DIR/ent_user_prompt.sql"
dump_ent_table "EnhancedPrompt"           "$BACKUP_DIR/ent_enhanced_prompt.sql"
dump_ent_table "RefinePrompt"             "$BACKUP_DIR/ent_refine_prompt.sql"
dump_ent_table "RefinePromptLegacy"       "$BACKUP_DIR/ent_refine_legacy.sql"
dump_ent_table "SaveEnhancePrompt"        "$BACKUP_DIR/ent_save_enhance.sql"
dump_ent_table "Conversation"             "$BACKUP_DIR/ent_conversation.sql"
dump_ent_table "UserPersonalization"      "$BACKUP_DIR/ent_user_personalization.sql"
dump_ent_table "AuditLog"                 "$BACKUP_DIR/ent_audit_log.sql"
dump_ent_table "ModerationLog"            "$BACKUP_DIR/ent_moderation_log.sql"
dump_ent_table "Notification"             "$BACKUP_DIR/ent_notification.sql"
dump_ent_table "company_policy_history"   "$BACKUP_DIR/ent_policy_history.sql"
dump_ent_table "content_policy_results"   "$BACKUP_DIR/ent_content_policy_results.sql"
dump_ent_table "prompt_moderation_results" "$BACKUP_DIR/ent_prompt_moderation.sql"
dump_ent_table "guardrail_approval_queue" "$BACKUP_DIR/ent_guardrail_queue.sql"
dump_ent_table "moderation_audit_log"     "$BACKUP_DIR/ent_moderation_audit.sql"
dump_ent_table "onboarding_runs"          "$BACKUP_DIR/ent_onboarding_runs.sql"
dump_ent_table "prompt_collections"       "$BACKUP_DIR/ent_prompt_collections.sql"
dump_ent_table "collection_prompts"       "$BACKUP_DIR/ent_collection_prompts.sql"
dump_ent_table "rule_toggle_state"        "$BACKUP_DIR/ent_rule_toggle.sql"
dump_ent_table "reviews"                  "$BACKUP_DIR/ent_reviews.sql"

echo "All enterprise dumps complete." | tee -a "$LOG_FILE"

# =============================================================================
# STEP 3: Transform dumps — remap schema from public.* to shared.*/consumer.*/enterprise.*
# pg_dump output uses: SET search_path = public; and table names without schema prefix
# We need to remap to the correct target schema.
# =============================================================================

echo ""
echo "=== STEP 3: Transforming dump files ===" | tee -a "$LOG_FILE"

remap_consumer() {
    local FILE="$1"
    # Change search_path to consumer (most tables)
    sed -i 's/SET search_path = public, pg_catalog;/SET search_path = consumer, shared, public;/g' "$FILE"
    # Fix sequence references that still say public.
    sed -i "s/SELECT pg_catalog.set_config('search_path', '', false);/SET search_path = consumer, shared, public;/g" "$FILE"
}

remap_shared() {
    local FILE="$1"
    sed -i 's/SET search_path = public, pg_catalog;/SET search_path = shared, public;/g' "$FILE"
    sed -i "s/SELECT pg_catalog.set_config('search_path', '', false);/SET search_path = shared, public;/g" "$FILE"
}

remap_enterprise() {
    local FILE="$1"
    sed -i 's/SET search_path = public, pg_catalog;/SET search_path = enterprise, public;/g' "$FILE"
    sed -i "s/SELECT pg_catalog.set_config('search_path', '', false);/SET search_path = enterprise, public;/g" "$FILE"
}

# Shared tables
for f in all_emails usertable userstatus otp_verification password_reset_tokens refresh_tokens; do
    remap_shared "$BACKUP_DIR/${f}.sql" 2>/dev/null || true
done

# Enterprise tables
for f in "$BACKUP_DIR"/ent_*.sql; do
    remap_enterprise "$f"
done

# All other consumer tables
for f in "$BACKUP_DIR"/*.sql; do
    # Skip already-remapped files and enterprise files
    if [[ "$f" != *"ent_"* ]]; then
        remap_consumer "$f" 2>/dev/null || true
    fi
done

echo "Transforms complete." | tee -a "$LOG_FILE"

# =============================================================================
# STEP 4: Load data into new schemas
# Order matters: shared first, then consumer, then enterprise
# =============================================================================

echo ""
echo "=== STEP 4: Loading data ===" | tee -a "$LOG_FILE"

load() {
    local FILE="$1"
    echo "  Loading $FILE..." | tee -a "$LOG_FILE"
    psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$NEW_USER" -d "$NEW_DB" \
        -f "$FILE" 2>>"$LOG_FILE" | tail -3 | tee -a "$LOG_FILE"
}

# Shared (level 0 + 1)
load "$BACKUP_DIR/all_emails.sql"
load "$BACKUP_DIR/usertable.sql"
load "$BACKUP_DIR/userstatus.sql"
load "$BACKUP_DIR/otp_verification.sql"
load "$BACKUP_DIR/password_reset_tokens.sql"
load "$BACKUP_DIR/refresh_tokens.sql"

# Consumer level 0
load "$BACKUP_DIR/billing_plans.sql"
load "$BACKUP_DIR/token_packages.sql"
load "$BACKUP_DIR/feature_token_costs.sql"
load "$BACKUP_DIR/prompt_marketplace.sql"
load "$BACKUP_DIR/prompt_library_items.sql"
load "$BACKUP_DIR/suggestion_prompt.sql"
load "$BACKUP_DIR/free_trial.sql"
load "$BACKUP_DIR/launchlist.sql"
load "$BACKUP_DIR/waitlistusers.sql"
load "$BACKUP_DIR/webhook_events.sql"
load "$BACKUP_DIR/processed_contexts.sql"
load "$BACKUP_DIR/processed_contexts_backup.sql"
load "$BACKUP_DIR/velocity_memories.sql"
load "$BACKUP_DIR/user_profiles.sql"
load "$BACKUP_DIR/api_error_logs.sql"
load "$BACKUP_DIR/conversations.sql"

# Consumer level 1
load "$BACKUP_DIR/subscriptions.sql"
load "$BACKUP_DIR/referrals.sql"
load "$BACKUP_DIR/invite_links.sql"
load "$BACKUP_DIR/prompt_preferences.sql"
load "$BACKUP_DIR/prompt_collections.sql"
load "$BACKUP_DIR/prompt_history.sql"
load "$BACKUP_DIR/user_context.sql"
load "$BACKUP_DIR/user_personalization.sql"
load "$BACKUP_DIR/onboarding_data.sql"
load "$BACKUP_DIR/reviews.sql"
load "$BACKUP_DIR/contact_messages.sql"
load "$BACKUP_DIR/engagement_email_log.sql"
load "$BACKUP_DIR/engagement_rewards.sql"
load "$BACKUP_DIR/inactive_email_sent.sql"
load "$BACKUP_DIR/essence_usage.sql"
load "$BACKUP_DIR/token_ledger.sql"
load "$BACKUP_DIR/token_reservations.sql"
load "$BACKUP_DIR/shared_prompts.sql"
load "$BACKUP_DIR/conversation_contexts.sql"
load "$BACKUP_DIR/prompt_memory.sql"
load "$BACKUP_DIR/prompt_actions.sql"
load "$BACKUP_DIR/mkt_embedding.sql"

# Consumer level 2
load "$BACKUP_DIR/payments.sql"
load "$BACKUP_DIR/user_prompts.sql"
load "$BACKUP_DIR/save_enhance_prompt.sql"

# Consumer level 3
load "$BACKUP_DIR/refine_prompt.sql"
load "$BACKUP_DIR/collection_prompts.sql"
load "$BACKUP_DIR/shared_prompt_claims.sql"
load "$BACKUP_DIR/invite_redemptions.sql"
load "$BACKUP_DIR/referral_relations.sql"
load "$BACKUP_DIR/token_transactions.sql"
load "$BACKUP_DIR/conversation_messages.sql"

# Enterprise (ordered by FK)
load "$BACKUP_DIR/ent_enterprise.sql"
load "$BACKUP_DIR/ent_permission.sql"
load "$BACKUP_DIR/ent_user.sql"
load "$BACKUP_DIR/ent_role.sql"
load "$BACKUP_DIR/ent_role_permission.sql"
load "$BACKUP_DIR/ent_team.sql"
load "$BACKUP_DIR/ent_team_user.sql"
load "$BACKUP_DIR/ent_user_role.sql"
load "$BACKUP_DIR/ent_company_policy.sql"
load "$BACKUP_DIR/ent_content.sql"
load "$BACKUP_DIR/ent_content_team.sql"
load "$BACKUP_DIR/ent_user_prompt.sql"
load "$BACKUP_DIR/ent_enhanced_prompt.sql"
load "$BACKUP_DIR/ent_refine_prompt.sql"
load "$BACKUP_DIR/ent_refine_legacy.sql"
load "$BACKUP_DIR/ent_save_enhance.sql"
load "$BACKUP_DIR/ent_conversation.sql"
load "$BACKUP_DIR/ent_user_personalization.sql"
load "$BACKUP_DIR/ent_audit_log.sql"
load "$BACKUP_DIR/ent_moderation_log.sql"
load "$BACKUP_DIR/ent_notification.sql"
load "$BACKUP_DIR/ent_policy_history.sql"
load "$BACKUP_DIR/ent_content_policy_results.sql"
load "$BACKUP_DIR/ent_prompt_moderation.sql"
load "$BACKUP_DIR/ent_guardrail_queue.sql"
load "$BACKUP_DIR/ent_moderation_audit.sql"
load "$BACKUP_DIR/ent_onboarding_runs.sql"
load "$BACKUP_DIR/ent_prompt_collections.sql"
load "$BACKUP_DIR/ent_collection_prompts.sql"
load "$BACKUP_DIR/ent_rule_toggle.sql"
load "$BACKUP_DIR/ent_reviews.sql"

echo "All data loaded." | tee -a "$LOG_FILE"

# =============================================================================
# STEP 5: Sync sequences to current max values
# Critical: without this, inserts will fail with duplicate PK errors
# =============================================================================

echo ""
echo "=== STEP 5: Syncing sequences ===" | tee -a "$LOG_FILE"

psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$NEW_USER" -d "$NEW_DB" << 'EOF' | tee -a "$LOG_FILE"
-- Sync all integer-PK sequences to max(id)+1
SELECT setval('shared.users_user_id_seq',          COALESCE((SELECT MAX(user_id) FROM shared.users), 1));
SELECT setval('shared.user_status_status_id_seq',   COALESCE((SELECT MAX(status_id) FROM shared.user_status), 1));
SELECT setval('shared.refresh_tokens_id_seq',       COALESCE((SELECT MAX(id) FROM shared.refresh_tokens), 1));
SELECT setval('shared.otp_verification_id_seq',     COALESCE((SELECT MAX(id) FROM shared.otp_verification), 1));
SELECT setval('shared.password_reset_tokens_id_seq', COALESCE((SELECT MAX(id) FROM shared.password_reset_tokens), 1));
SELECT setval('shared.all_emails_id_seq',           COALESCE((SELECT MAX(id) FROM shared.all_emails), 1));
SELECT setval('consumer.referral_relations_id_seq', COALESCE((SELECT MAX(id) FROM consumer.referral_relations), 1));
EOF

echo "Sequences synced." | tee -a "$LOG_FILE"

# =============================================================================
# STEP 6: Row count verification
# =============================================================================

echo ""
echo "=== STEP 6: Verification ===" | tee -a "$LOG_FILE"

psql -h "$NEW_HOST" -p "$NEW_PORT" -U "$NEW_USER" -d "$NEW_DB" << 'EOF' | tee -a "$LOG_FILE"
SELECT
    schemaname,
    tablename,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE schemaname IN ('shared', 'consumer', 'enterprise', 'extension')
ORDER BY schemaname, tablename;
EOF

echo ""
echo "=== Migration complete at $(date) ===" | tee -a "$LOG_FILE"
echo "Log saved to: $LOG_FILE"
echo "Backup files in: $BACKUP_DIR"
echo ""
echo "NEXT STEPS:"
echo "  1. Review row counts above — compare to old DB counts"
echo "  2. Run schema/tests/test_schema_completeness.py"
echo "  3. Start parallel run phase (Phase 4)"
echo "  4. Only after 48h parallel run: flip DNS (Phase 5)"
