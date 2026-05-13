# ThinkVelocity Design Direction

## Context

The app is a local FastAPI prompt engineering workspace. The product surface needs to make prompt enhancement feel inspectable rather than opaque: users should see the generated prompt, the reasoning techniques behind each segment, reusable placeholders, memory context, and persona movement from repeated usage.

## Inspiration

Primary inspiration is the Codex desktop interface: a focused left navigation rail, a central conversation/workspace, and a right-side context/details panel. The design avoids a marketing landing page and starts directly in the working surface.

## Workspace Decisions

- Use a three-column app shell: left sidebar for new chat, examples, history, and Brain access; center workspace for raw prompt and enhanced output; right panel for branch details.
- Treat each enhancement as a thread message so users can scan the conversation and restore history without losing context.
- Keep visual styling restrained: dark surfaces, thin borders, compact typography, and deliberate accent use. This matches a work tool instead of a decorative SaaS page.
- Keep the composer anchored at the bottom like an agent workspace. The prompt output remains above it in the thread.

## Annotation Decisions

- Annotated mode is the default because it is the key product differentiator.
- Each `annotated_segment` renders inline with a technique-colored left border and low-opacity background.
- Segment hover explains the technique and reason. Segment click allows inline editing so users can tune the enhanced prompt without leaving the annotated view.
- Plain mode remains available for fast copying and manual editing.

## Placeholder Details

- Placeholder-heavy prompts are first-class. The enhancement engine now returns `placeholder_fields`.
- Placeholder technique key: `placeholder_facilitation`.
- Placeholder color key: `slate`.
- Placeholders are normalized as uppercase square-bracket blanks, for example `[TARGET_AUDIENCE]`.
- The right panel renders each placeholder as a fill-in-the-blank input. Applying blanks replaces matching placeholder tokens in the annotated segments and assembled prompt.

## Branch Details Panel

The right panel shows:

- Framework and rationale
- Intent, domain, quality score, and target optimization
- Current user context summary
- Annotation technique list
- Placeholder inputs
- Clarification/refine controls

This keeps prompt details close to the active output without crowding the center thread.

## Brain View

The Brain is a separate workspace view reached from the left sidebar memory button.

- The center graph displays user, domain, intent, prompt context, preference, and personalization nodes.
- Clicking a node toggles a node inspector with the underlying prompt/context data.
- The right side of the Brain view shows persona metrics calculated from current memory context.

## Persona Calculation

Persona is intentionally simple and local:

- `Template Architect`: high placeholder usage
- `Strategy Builder`: strategy-heavy recent intent movement
- `Technical Builder`: software domain concentration
- `Growth Operator`: marketing/growth domain concentration
- `Cross-Domain Explorer`: broad repeated usage across multiple prompt types
- `New Operator`: insufficient history

Metrics use enhancement count, domain count, unique intent count, and total placeholder count.

## Implementation Notes

- No new backend service was added.
- Storage remains JSON-file based.
- The UI uses vanilla HTML/CSS/JS and `vis-network` from CDN, consistent with the build spec.
- CORS remains open for local development and direct static testing.

## 2026-05-07 Refinement Pass

- Removed visible product branding from the application shell. The workspace now starts directly with navigation and the prompt composer.
- Removed prompt examples and the "Load example" button because the MVP should focus on the user's actual prompt, not canned prompts.
- Removed manual memory note entry. Memory is now represented in the UI only from automatically generated prompt metadata: intent, domain, framework, summary, and placeholder count.
- Mobile layout now forces the chat interface only. Sidebar, right details, topbar, and Brain view are hidden on small screens.
- Added direct result-level actions: `Refine` and `Before / After`.
- Right sidebar sections are interactive. Strategy, intent, domain, quality, context metrics, and prompt techniques are clickable markers that reveal only the necessary explanation.
- Empty right-sidebar states no longer explain unavailable features. Content appears only when there is useful or actionable data.

## 2026-05-07 Sandbox Naming and Flow Pass

- Renamed the visible product surface to "Prompt Enhancement Sandbox".
- Added left and right sidebar toggles so the user can collapse navigation or details while staying in the prompt flow.
- Changed refinement to always present three multiple-choice questions. This keeps refinement fast and removes open-ended form friction.
- Added deterministic backend quality ceilings so very short prompts cannot receive inflated quality scores.
- Brain expectations: the Brain is not a manual note system. It is an auto-built map of prompt metadata showing the user node, inferred domains, inferred intents, recent prompt summaries, strategies/frameworks used, placeholder count, and a simple persona calculated from those signals.

## 2026-05-07 Senior Design and Prompt Review

- Added a custom refinement instruction field below the three multiple-choice questions. The user's freeform refinement instruction is submitted as a high-priority refinement constraint.
- Replaced the Brain hard failure state with a native fallback graph. If `vis-network` does not load from CDN, users still see clickable metadata nodes.
- Refined card styling for prompt blanks, refinement questions, and persona metrics with clearer hierarchy, softer elevation, and less raw diagnostic text.
- Updated enhancement and refinement system prompts to explicitly operate from a senior prompt-engineering standard: preserve real intent, avoid invented facts, use placeholders for unknowns, and keep outputs directly usable by non-expert users.
