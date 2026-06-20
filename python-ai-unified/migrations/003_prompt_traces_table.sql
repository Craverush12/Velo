CREATE TABLE IF NOT EXISTS prompt_traces (
    id              SERIAL PRIMARY KEY,
    trace_id        UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id         TEXT        NOT NULL,
    session_id      TEXT,
    platform        TEXT,
    domain          TEXT,
    intent          TEXT,
    raw_prompt      TEXT,
    enhanced_prompt TEXT,
    context_hint    TEXT,
    persona_hint    TEXT,
    suggested_ai    TEXT,
    model           TEXT,
    tokens_in       INT,
    tokens_out      INT,
    latency_ms      INT,
    quality_score   FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_traces_user_created ON prompt_traces(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_domain       ON prompt_traces(domain);
CREATE INDEX IF NOT EXISTS idx_traces_created      ON prompt_traces(created_at DESC);
