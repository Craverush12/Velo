# Node backend endpoint needed: user persona (public, read-only)

## Why

`python-ai-unified` now has a `_fetch_user_persona(user_id)` function (in
`routers/ai/enhance.py`) that's wired into both Enhance and Refine, ready to
inject a stable "who this user is" block into every LLM call — alongside the
existing `session_essence` ("what they're working on right now"). It degrades
open today because **the endpoint it calls doesn't exist yet.**

This closes a real gap: `onboarding_data` and `user_personalization` are
already collected (onboarding flow + Profile Page) but never reach the
enhance/refine pipeline at all today.

## What's needed

One new route on the Node backend, mirroring the existing public/no-auth
pattern already used for context search (`/api/v1/processed-context/public/*`):

```
GET /api/v1/personalization/public/:userId
```

- **No auth required** — same trust model as the existing public context
  endpoints (internal Docker network only, `tv-node-backend:3005`, never
  exposed publicly).
- **Read-only.** Do not add a write path here — writes already go through
  the authenticated `/api/personalization/*` routes.
- Combine two existing tables, both already populated:
  - `onboarding_data` (via `getOnboardingData(userId)` in `models/userModel.js`)
  - `user_personalization` (via the personalization model)

### Expected response shape

```json
{
  "onboarding": {
    "llm_platform": "chatgpt",
    "occupation": "marketer",
    "ai_familiarity": "Beginner"
  },
  "personalization": {
    "preferred_name": "Arjun",
    "professional_world": "B2B SaaS, prompt engineering tools",
    "velocity_traits": "concise, technical",
    "personal_life": null,
    "hobbies": null,
    "primary_model": "claude"
  }
}
```

- Either top-level key may be `null` if that user has no row in that table —
  this is the normal/expected case for most users, not an error.
- If the user has **neither** row, return `200` with both keys `null`
  (or `404` — the python-side client treats both as "no persona yet" and
  degrades to an empty hint either way, so either is fine; `200` is simpler).
- `discovery_channel`/`discovery_detail`/`source` from `onboarding_data` and
  any other column not listed above are intentionally omitted — these are
  acquisition/marketing fields, not useful for prompt personalization. Add
  more fields later only if there's a concrete reason to feed them to the LLM.

### Example implementation sketch (illustrative, adapt to actual conventions)

```js
router.get("/public/:userId", async (req, res) => {
  const { userId } = req.params;
  const [onboarding, personalization] = await Promise.all([
    getOnboardingData(userId).catch(() => null),
    getPersonalization(userId).catch(() => null), // existing model fn
  ]);
  res.json({
    onboarding: onboarding
      ? {
          llm_platform: onboarding.llm_platform,
          occupation: onboarding.occupation,
          ai_familiarity: onboarding.ai_familiarity,
        }
      : null,
    personalization: personalization
      ? {
          preferred_name: personalization.preferred_name,
          professional_world: personalization.professional_world,
          velocity_traits: personalization.velocity_traits,
          personal_life: personalization.personal_life,
          hobbies: personalization.hobbies,
          primary_model: personalization.primary_model,
        }
      : null,
  });
});
```

## What happens once this ships

No python-ai-unified deploy needed — the client code is already live and
calling this URL today, just getting empty results. The moment this route
returns real data, `persona_hint` starts flowing into every enhance/refine
call automatically.

## Where this needs to land

**Not clear from this repo.** `FullCodebase/ThinkVelocity/backend-V1/` looks
like the right code (has `onboardingController.js`, `personalizationModel.js`,
matching route patterns) but:
- The CI/CD workflow that's supposed to deploy the Node backend
  (`.github/workflows/deploy-nodejs-backend.yml`) triggers on `backend/**`,
  a path that doesn't exist anywhere in this repo — so that pipeline has
  likely never successfully fired.
- `tv-node-backend` on the production server runs a **pre-built image
  pulled from Docker Hub** (`thinkvelocity24/thinkvelocity-backend:latest`),
  not something built live from this repo's source the way
  `python-ai-unified`/`extension-api` are.

Confirmed with the team (2026-06-16): this repo is **not** the source of
truth for the Node.js backend. Whoever has access to the actual Node repo
needs to add this route there, then go through whatever that repo's real
build → push → deploy pipeline is.
