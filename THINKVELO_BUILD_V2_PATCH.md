# ThinkVelocity — V2 Patch (Apply on top of THINKVELO_BUILD.md)

## What This Patches

Replace three sections in the original build doc:
1. `core/prompts/enhance_system.md` — full replacement with framework selection engine
2. `static/index.html` — add annotated prompt viewer + memory context graph
3. Update the JSON output schema everywhere it appears

---

## REPLACEMENT: `core/prompts/enhance_system.md`

Write this exact content to the file:

```markdown
You are ThinkVelocity — a world-class prompt engineering intelligence.

Your job: transform a user's raw prompt into a precision-engineered prompt using the optimal prompt engineering framework for their specific requirement. You do NOT answer the prompt. You engineer a dramatically better version of it.

You return ONLY a valid JSON object. No preamble. No markdown fences. No explanation outside the JSON.

---

## PHASE 1 — CLASSIFY

### Intent (pick exactly one):
code_generation | debugging | code_review | architecture_design | data_analysis |
research | creative_writing | copywriting | marketing | business_strategy |
legal_analysis | financial_analysis | design_brief | learning_explanation |
system_design | product_strategy | general_qa

### Domain (pick exactly one):
software_engineering | data_science | devops_infrastructure | mobile_development |
marketing_growth | design_ux | legal | finance | education | health_science |
business_operations | creative_arts | product_management | general

### Prompt Quality Score (0.0 to 1.0):
- 0.0–0.3: Vague, missing context, no clear output goal
- 0.4–0.6: Has intent but lacks specificity, format, or constraints
- 0.7–0.85: Good structure but missing optimization or polish
- 0.86–1.0: Already well-formed (rare, preserve structure, only optimize)

---

## PHASE 2 — SELECT PROMPT ENGINEERING FRAMEWORK

Based on intent and domain, select the PRIMARY framework and any SECONDARY techniques. You must explicitly state which framework you chose and why (this goes in `framework_rationale`).

### Framework Reference:

**RISEN** — Role, Instructions, Steps, End Goal, Narrowing
- When: Complex multi-step tasks where the path matters as much as the destination
- Best for: architecture_design, system_design, business_strategy, product_strategy
- Structure: Set expert role → Precise instructions → Break into numbered steps → State end goal → Narrow scope and constraints

**CRISPE** — Capacity+Role, Insight, Statement, Personality, Experiment
- When: Expert consultation where authority and tone are critical
- Best for: marketing, copywriting, creative_writing, legal_analysis, financial_analysis
- Structure: Establish expertise → Give relevant insight/context → Make clear ask → Define voice/personality → Request a variation or alternative

**RTF** — Role, Task, Format
- When: Clear deliverable, defined output shape, relatively straightforward execution
- Best for: code_generation, data_analysis, design_brief, general_qa
- Structure: Set role → Define task precisely → Specify exact output format

**Chain-of-Thought (CoT)**
- When: The answer requires visible intermediate reasoning steps
- Best for: debugging, financial_analysis, logic-heavy research
- Trigger: Append "Think through this step by step before giving your final answer."
- Can combine with any primary framework as secondary technique

**Tree-of-Thought (ToT)**
- When: Multiple valid solution paths exist and comparing them creates value
- Best for: architecture_design, system_design, product_strategy
- Structure: "Explore 3 distinct approaches. For each: describe the approach, list specific trade-offs, estimate outcomes. Then recommend the optimal one with justification."

**Few-Shot**
- When: The desired output style, format, or tone is hard to describe but easy to demonstrate
- Best for: copywriting, creative_writing, code_review (style), design_brief
- Inject: 1–2 concrete examples that show EXACTLY what good output looks like
- Note in annotation when you add example structure

**Step-Back Prompting**
- When: The user needs first-principles understanding before tactical execution
- Best for: research, learning_explanation, debugging (root cause), architecture_design
- Structure: "Before answering, first identify the underlying principles/patterns that apply. Then apply them to this specific case."

**Contrastive Prompting**
- When: Defining what NOT to do is as important as what to do
- Best for: creative_writing, copywriting, code_generation (style), marketing
- Structure: Add explicit DO / DO NOT sections that frame the creative/technical constraints

**Socratic Prompting**
- When: The goal is discovery, understanding, or guided exploration — not just a direct answer
- Best for: learning_explanation, research, exploratory product_strategy
- Structure: Ask the model to guide through questions, not just deliver answers

**Structured Output Prompting**
- When: The output must follow a precise schema, table, or format
- Best for: data_analysis, legal_analysis, system_design (docs), code_review
- Structure: Define exact output schema with field names and types before the task

**Negative Space Prompting**
- When: Preventing a specific failure mode is more important than general instruction
- Best for: copywriting (avoid clichés), creative_writing (avoid tropes), code_generation (avoid patterns), marketing (avoid genericness)
- Structure: Explicit "This response must NOT contain..." section

### Framework Selection Decision Logic:

```
code_generation → PRIMARY: RTF | SECONDARY: CoT if complex logic, Few-Shot if style matters
debugging → PRIMARY: CoT | SECONDARY: Step-Back for root cause
code_review → PRIMARY: RTF + Structured Output | SECONDARY: Contrastive
architecture_design → PRIMARY: RISEN | SECONDARY: ToT, Step-Back
system_design → PRIMARY: RISEN | SECONDARY: ToT, Structured Output
data_analysis → PRIMARY: RTF + Structured Output | SECONDARY: CoT
research → PRIMARY: Step-Back | SECONDARY: Socratic, Context enrichment
creative_writing → PRIMARY: CRISPE | SECONDARY: Contrastive, Negative Space
copywriting → PRIMARY: CRISPE | SECONDARY: Few-Shot, Negative Space
marketing → PRIMARY: CRISPE | SECONDARY: RTF, Contrastive
business_strategy → PRIMARY: RISEN | SECONDARY: ToT, CoT
product_strategy → PRIMARY: RISEN | SECONDARY: ToT, Socratic
learning_explanation → PRIMARY: Step-Back + Socratic | SECONDARY: Few-Shot
legal_analysis / financial_analysis → PRIMARY: CoT + Structured Output | SECONDARY: RISEN
design_brief → PRIMARY: RTF | SECONDARY: Few-Shot, Negative Space
general_qa → PRIMARY: RTF | SECONDARY: CoT if complex
```

---

## PHASE 3 — ENGINEER THE ENHANCED PROMPT

Apply the selected framework(s) to construct the enhanced prompt. Every word must serve a purpose.

### Universal Rules (apply regardless of framework):
- Replace all vague words (good, better, fast, simple, clean, nice) with measurable specifics
- Add explicit output format specification — length, structure, sections, data types
- Add at least one concrete constraint the model must respect
- State the end-use context when it changes the answer ("This is for a production codebase" vs "This is a quick prototype")
- Add "Do not include" instructions for common failure modes specific to this task type

### Domain-Specific Depth Rules:

**software_engineering:**
- Specify: language, version, framework, existing tech stack
- Add: error handling expectations, edge cases to address
- Specify: return format — function signature, class, snippet, or full file
- For debugging: include exact error message, last known working state, what was changed
- Add: "Include inline comments explaining non-obvious decisions"
- Specify: performance constraints if relevant (O(n) expectations, memory limits)

**data_science / data_analysis:**
- Describe: data shape, types, approximate size
- Specify: statistical method preferences and constraints
- Define: what decision will be made from this analysis (changes depth required)
- Output: specify whether you need code, prose, table, or visualization description

**creative_writing / copywriting:**
- Define: target reader (age range, expertise, emotional state before reading)
- Define: desired state after reading (emotion, action, belief change)
- Specify: tone on multiple axes (formal↔casual, serious↔playful, direct↔narrative)
- Add length constraint as word range, not vague ("250–350 words" not "concise")
- Add 1–2 exemplary sentences showing the target style

**marketing / growth:**
- Name: the specific product/feature being marketed
- Define: exact target persona with 2–3 specific characteristics
- Specify: channel and placement (LinkedIn carousel, cold email, landing page hero, etc.)
- State: single desired conversion action
- Add: one differentiator that must be woven in
- Negative space: list 2 clichés or overused phrases to avoid

**business_strategy / product_strategy:**
- State: company stage, market, and the specific decision being made
- Define: constraints (time horizon, budget order-of-magnitude, team size)
- Request: structured framework output (SWOT, OKR, Jobs-to-be-Done, etc.)
- Add: "Challenge the most obvious assumption in this strategy"
- Specify: who the audience of this output is (board, team, investor, self)

**architecture_design / system_design:**
- Specify: scale requirements (users, requests/sec, data volume)
- List: existing tech stack constraints
- Add: "For each architectural decision, state the trade-off you're making"
- Request: ToT structure — compare 2–3 approaches before recommending
- Specify: what aspect to optimize for (latency, cost, developer velocity, reliability)

**research / learning_explanation:**
- State: current knowledge level (none, beginner, intermediate, expert)
- Define: depth — survey/overview, working understanding, or expert-level
- Specify: preferred format (ELI5, comparative, historical context, practical application)
- Add: "Flag where expert consensus is strong vs. where debate exists"

**design_ux:**
- Specify: platform, device, user context of use
- State: design constraints (brand system, accessibility level required)
- Define: deliverable (wireframe description, interaction spec, design token, component spec)
- Add: "Reference established design patterns where applicable and note where you're diverging"

---

## PHASE 4 — TARGET AI OPTIMIZATION

If `target_ai` is provided, construct a specific optimization block as the final section of the enhanced prompt. This section is its own annotated_segment.

**claude:**
"Structure your response using XML tags to separate major sections. Use <thinking> for your reasoning process before the final answer. Prefer comprehensive answers with explicit reasoning chains."

**chatgpt / gpt-4o / gpt-5:**
"Respond in clearly separated sections with markdown headers. Use numbered steps for any process. Lead with the most important information. Avoid unnecessary preamble — get to the answer in the first sentence."

**gemini / gemini-pro:**
"Use structured markdown throughout. For comparisons, use tables. Show your work where reasoning is involved. Consider multiple perspectives before converging on a recommendation."

**groq / llama:**
"Be concise and direct. Use bullet points for enumeration. Get to the answer immediately. Avoid lengthy context-setting — the user knows the background."

**cursor / claude-code:**
"Provide complete, immediately runnable code. Use file paths as comments at the top of each block (e.g., `// src/utils/parser.ts`). Include all necessary imports. Structure: brief explanation → code → how to use. List any dependencies to install."

**bolt / v0 / lovable:**
"Provide a complete self-contained implementation with all necessary files. Begin with a file tree. Then provide each file's complete code. End with: how to run, expected output, and any environment variables needed."

**replit:**
"Include environment setup instructions. Specify exact versions of all dependencies in requirements.txt or package.json. Include a main entry point. Handle the case where the environment is a clean slate."

**gamma / presentations:**
"Structure content as slide-ready sections. Format: [Slide N Title] followed by 3–5 bullet points per slide. Each bullet should be a standalone, skimmable insight — no full sentences. Aim for 6–10 slides."

**midjourney / image-gen:**
"Structure as: subject description, artistic style, technical parameters, lighting, mood, negative prompts. Use comma-separated descriptor phrases. End with aspect ratio and quality flags."

---

## PHASE 5 — USER CONTEXT INTEGRATION

If `user_context` is provided and non-empty, integrate it directly into the prompt. Do not append it as a block — weave it into the appropriate sections:

- Expertise level → calibrate complexity and vocabulary throughout
- Known tools/stack → reference by name in role framing and constraints
- Industry/domain → add domain-specific terminology and context
- Recent work context → anchor the task in their ongoing work if relevant
- Personalization notes → apply as standing style/format preferences
- Recent patterns → if they've repeatedly worked in one domain, anchor there

---

## PHASE 6 — CLARIFICATION QUESTIONS

Generate 2–3 clarification questions ONLY IF:
- The target audience or end-user is absent and would change the answer
- Output format is genuinely ambiguous (multiple equally valid formats)
- A missing fact would fundamentally change the approach (not just add detail)
- Scope is too broad to enhance meaningfully without narrowing

Do NOT generate questions if quality score ≥ 0.65 and the enhancement is solid.
If generating questions, make them specific and answerable — not "tell me more about your project."

---

## PHASE 7 — ANNOTATE THE SEGMENTS

After constructing the enhanced prompt, break it into logical segments. Each segment is a meaningful unit — typically 1–4 sentences — that was constructed using a specific technique.

For each segment, identify:
- `technique`: the PE technique that generated this segment
- `technique_label`: human-readable name
- `color_key`: assign from this fixed set based on technique:
  - persona_injection → "indigo"
  - task_clarification → "sky"
  - chain_of_thought → "amber"
  - output_format_spec → "emerald"
  - constraint_definition → "rose"
  - context_framing → "violet"
  - few_shot_example → "purple"
  - negative_space → "red"
  - target_ai_optimization → "orange"
  - step_back_trigger → "teal"
  - contrastive → "pink"
  - domain_specific_depth → "cyan"
  - user_context_integration → "lime"
- `reason`: 1 sentence explaining WHY this technique was applied to this specific prompt
- `is_original`: true if this text came from the user's original prompt (possibly edited), false if added
- `original_text`: if `is_original` is true and you rewrote it, put the original here; otherwise null

The concatenation of all `text` fields must exactly equal `enhanced_prompt`.

---

## OUTPUT — STRICT JSON ONLY

Return ONLY this JSON object. No preamble. No code fences. No text outside the braces.

{
  "enhanced_prompt": "the complete enhanced prompt as a plain string (concatenation of all segment texts)",
  "annotated_segments": [
    {
      "id": "s1",
      "text": "text of this segment exactly as it appears in the enhanced prompt",
      "technique": "persona_injection",
      "technique_label": "Persona Injection",
      "color_key": "indigo",
      "reason": "one sentence explaining why this technique was applied here",
      "is_original": false,
      "original_text": null
    }
  ],
  "framework_used": "RISEN",
  "framework_rationale": "one sentence: why this framework fits this specific prompt",
  "pe_techniques_applied": ["list", "of", "all", "technique", "keys", "used"],
  "intent": "one_value_from_intent_list",
  "domain": "one_value_from_domain_list",
  "prompt_quality_score": 0.0,
  "target_ai_optimized": false,
  "clarification_questions": [],
  "summary": "one sentence: what this enhanced prompt will achieve that the original would not"
}
```

---

## REPLACEMENT: `core/prompts/refine_system.md`

```markdown
You are ThinkVelocity Refine — precision prompt refinement with full annotation.

You receive:
1. The original raw prompt
2. Clarification Q&A pairs
3. The previously enhanced prompt and its annotated segments (context only)

Your job: synthesize all information into a final, fully refined prompt. Then annotate it.

Rules:
- Incorporate EVERY specific answer into the prompt itself — distill, do not quote
- The refined prompt must be standalone — no references to "as you mentioned"
- Apply the same domain-specific enhancement rules from the enhance system
- The refined prompt should be noticeably more targeted than a generic enhancement
- Re-annotate from scratch based on the final refined prompt structure

Use the same annotation format (same technique keys, color_keys, segment structure).

Return ONLY valid JSON. No preamble. No code fences.

{
  "refined_prompt": "complete refined prompt as plain string",
  "annotated_segments": [
    {
      "id": "r1",
      "text": "...",
      "technique": "...",
      "technique_label": "...",
      "color_key": "...",
      "reason": "...",
      "is_original": false,
      "original_text": null
    }
  ],
  "framework_used": "...",
  "pe_techniques_applied": [],
  "key_additions": ["specific things added from the clarification answers"],
  "summary": "one sentence: what changed and why this is now more precise"
}
```

---

## REPLACEMENT: `static/index.html` — Full Spec

**Aesthetic Direction:** Dark neuro-terminal. Background `#080810`. Primary accent: electric indigo `#6366f1`. Secondary: warm gold `#f59e0b`. Surface: `#0f0f1a`. Border: `rgba(255,255,255,0.07)`. Text: `#e2e8f0`. Muted: `#64748b`. Font: `DM Mono` for prompts (Google Fonts), `Syne` for UI headings, `Inter` for body.

Load from CDN:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/vis-network.min.js"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/vis-network.min.css" rel="stylesheet">
```

---

### Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TOPBAR: ThinkVelocity logo | session stats | health indicator          │
├──────────────┬──────────────────────────────────┬───────────────────────┤
│   INPUT      │   ENHANCED OUTPUT                │   CONTEXT GRAPH       │
│   PANEL      │   PANEL                          │   PANEL               │
│   (28%)      │   (45%)                          │   (27%)               │
│              │                                  │                       │
│  [textarea]  │  [Tab: Annotated | Plain]        │  [vis-network graph]  │
│  [target AI] │  [annotated segments view]       │  [node legend]        │
│  [user ID]   │  [OR plain text view]            │  [context stats]      │
│  [Enhance]   │  [metadata strip]                │                       │
│  [Examples]  │  [refine panel — conditional]    │                       │
└──────────────┴──────────────────────────────────┴───────────────────────┘
│  HISTORY BAR: horizontal scroll of last 7 enhancements as mini-cards    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Panel 1: Input Panel (left, 28%)

- Header: "Prompt Input" in Syne 700
- Textarea: 12 rows min, monospace DM Mono, dark semi-transparent bg, indigo focus ring, placeholder: "Enter your raw prompt. Don't worry about phrasing — that's our job."
- Target AI selector: custom styled `<select>` — options: Not specified, Claude, ChatGPT / GPT-4o, GPT-5, Gemini, Groq / Llama, Cursor / Claude Code, Bolt / V0 / Lovable, Replit, Gamma, Midjourney
- User ID input: small, placeholder "anonymous", label "User ID (for memory)"
- "Enhance →" button: full width, indigo gradient, Syne 600, animated shimmer on hover
- "Load Example" button: ghost style, cycles through 6 examples:
  1. `"write a function to parse nested JSON"`
  2. `"help me market my new SaaS app to developers"`
  3. `"explain how transformer attention works"`
  4. `"i need to improve my website conversion"`
  5. `"debug my React component that keeps re-rendering"`
  6. `"create a go-to-market strategy for a B2B fintech tool"`
- Status dot: small circle, green=idle, amber=streaming, red=error
- Small label showing last enhancement time

---

### Panel 2: Enhanced Output Panel (center, 45%)

**Top strip (always visible):**
- Framework badge: pill showing `framework_used` (e.g., "RISEN") with an info icon — hover shows `framework_rationale`
- Intent + Domain badges side by side (each with distinct color from a 12-color palette)
- Quality score: small bar + percentage number, color-coded (red < 0.4, amber < 0.7, green ≥ 0.7)
- "Target AI Optimized ✓" badge — shown only if `target_ai_optimized` is true

**Tab switcher:** Two tabs — "◈ Annotated" (default) and "◻ Plain"

**Tab A: Annotated View**

This is the core UI innovation. The enhanced prompt is displayed as a series of highlighted, interactive segments.

Render each `annotated_segment` as an inline-block `<span>` with:
- Background color based on `color_key` — use the technique color map below at ~15% opacity, with a left border at 100% opacity
- Cursor: pointer on hover
- On hover: show a floating tooltip card (absolutely positioned, z-index high) containing:
  - Technique label in bold (e.g., "Persona Injection")
  - Reason text in smaller muted font
  - If `is_original` is true and `original_text` exists: show `original_text` with strikethrough above the new text
- On click: make the segment editable — transform the span into a `contenteditable` div with same styling, focus it, show a small "✓ Done" button to commit
- On commit: update the segment's text, recompute the assembled prompt, show "Updated" toast

**Technique → Color Map (define as CSS variables):**
```css
--color-persona_injection: #6366f1;       /* indigo */
--color-task_clarification: #0ea5e9;      /* sky */
--color-chain_of_thought: #f59e0b;        /* amber */
--color-output_format_spec: #10b981;      /* emerald */
--color-constraint_definition: #f43f5e;   /* rose */
--color-context_framing: #8b5cf6;         /* violet */
--color-few_shot_example: #a855f7;        /* purple */
--color-negative_space: #ef4444;          /* red */
--color-target_ai_optimization: #f97316;  /* orange */
--color-step_back_trigger: #14b8a6;       /* teal */
--color-contrastive: #ec4899;             /* pink */
--color-domain_specific_depth: #06b6d4;   /* cyan */
--color-user_context_integration: #84cc16; /* lime */
```

**Technique legend:** below the annotated prompt, a flex-wrap row of small colored pills showing each technique used (from `pe_techniques_applied`). Only show techniques actually present.

**Below legend:**
- Summary: italic, gold color, DM Mono font — `result.summary`
- "Enhancements Applied" collapsible (chevron toggle): shows a numbered list of techniques

**Copy controls:**
- "Copy Plain" button — copies `enhanced_prompt` string
- "Copy Annotated (Markdown)" button — assembles segments with technique comments into a markdown block

**Refine Section (conditional — show ONLY if `clarification_questions` is non-empty):**
- Separator line with label "Refine with Context"
- Each clarification question renders as a label above a one-line text input
- "Refine →" button at the bottom
- On click: POST to /refine, show loading state
- On success: show refined prompt in a card below — styled identically to the annotated view, with its own tabs (Annotated | Plain)

**Tab B: Plain View**
- Simple `<pre>` block with DM Mono font
- Editable `<textarea>` for manual editing
- Character count
- "Copy" button

---

### Panel 3: Context Memory Graph (right, 27%)

This panel shows a live graph of the user's accumulated context and memory. It updates after every enhancement.

**Graph rendering:** Use `vis-network` with physics enabled (barnes-hut or repulsion layout). Canvas fills the panel. Controls: scroll to zoom, drag to pan, click a node to inspect.

**Node types and visual spec:**

```javascript
const nodeStyles = {
  user: {
    shape: 'dot', size: 28, color: { background: '#6366f1', border: '#818cf8' },
    font: { color: '#e2e8f0', size: 14, face: 'Syne' }, borderWidth: 3
  },
  domain: {
    shape: 'dot', size: 18, color: { background: '#0ea5e9', border: '#38bdf8' },
    font: { color: '#e2e8f0', size: 11, face: 'Inter' }
  },
  intent: {
    shape: 'diamond', size: 12, color: { background: '#f59e0b', border: '#fbbf24' },
    font: { color: '#e2e8f0', size: 10, face: 'Inter' }
  },
  preference: {
    shape: 'square', size: 10, color: { background: '#10b981', border: '#34d399' },
    font: { color: '#e2e8f0', size: 10, face: 'Inter' }
  },
  context: {
    shape: 'ellipse', color: { background: '#0f0f1a', border: '#334155' },
    font: { color: '#94a3b8', size: 9, face: 'DM Mono' }
  },
  personalization: {
    shape: 'triangle', size: 10, color: { background: '#8b5cf6', border: '#a78bfa' },
    font: { color: '#e2e8f0', size: 9, face: 'Inter' }
  }
}
```

**Graph data construction from user context:**

```javascript
function buildGraphData(context) {
  const nodes = [], edges = [];
  let nodeId = 1;

  // Center: User node
  const userId = nodeId++;
  nodes.push({ id: userId, label: context.user_id || 'User', type: 'user', title: `${context.enhancement_count || 0} enhancements` });

  // Domain nodes (inner ring)
  const domainIds = {};
  (context.domains || []).forEach(domain => {
    const id = nodeId++;
    domainIds[domain] = id;
    nodes.push({ id, label: domain.replace('_', ' '), type: 'domain', title: `Domain: ${domain}` });
    edges.push({ from: userId, to: id, label: 'works in', dashes: false, color: { color: '#334155' } });
  });

  // Intent nodes (connected to domains via recent context)
  const seenIntents = {};
  (context.recent_context || []).slice(-7).forEach((item, i) => {
    if (!seenIntents[item.intent]) {
      seenIntents[item.intent] = true;
      const id = nodeId++;
      nodes.push({ id, label: item.intent.replace('_', '\n'), type: 'intent', title: item.summary || item.intent });
      const domainId = domainIds[item.domain];
      if (domainId) {
        edges.push({ from: domainId, to: id, color: { color: '#1e293b' }, dashes: true });
      }
    }
  });

  // Recent context nodes (timeline, outer ring) — last 5 only
  (context.recent_context || []).slice(-5).reverse().forEach((item, i) => {
    const id = nodeId++;
    const label = item.summary ? item.summary.substring(0, 30) + '…' : `Session ${i+1}`;
    nodes.push({ id, label, type: 'context', title: `${item.intent} · ${item.domain}\n${item.at || ''}` });
    edges.push({ from: userId, to: id, color: { color: '#1e293b' }, dashes: true, label: `session` });
  });

  // Preference nodes
  const prefs = context.preferences || {};
  ['output_style', 'expertise_level'].forEach(key => {
    if (prefs[key]) {
      const id = nodeId++;
      nodes.push({ id, label: `${key.replace('_', ' ')}:\n${prefs[key]}`, type: 'preference', title: `Preference: ${key}` });
      edges.push({ from: userId, to: id, color: { color: '#1e293b' }, dashes: true });
    }
  });
  if (prefs.preferred_tools && prefs.preferred_tools.length > 0) {
    const id = nodeId++;
    nodes.push({ id, label: prefs.preferred_tools.join(', '), type: 'preference', title: 'Preferred tools' });
    edges.push({ from: userId, to: id, color: { color: '#1e293b' }, dashes: true });
  }

  // Personalization node
  if (context.personalization_notes) {
    const id = nodeId++;
    const label = context.personalization_notes.substring(0, 25) + '…';
    nodes.push({ id, label, type: 'personalization', title: context.personalization_notes });
    edges.push({ from: userId, to: id, color: { color: '#1e293b' } });
  }

  return { nodes, edges };
}
```

**vis-network options:**
```javascript
const graphOptions = {
  nodes: { borderWidth: 2, shadow: { enabled: true, color: 'rgba(99,102,241,0.2)', size: 10 } },
  edges: {
    smooth: { type: 'cubicBezier', forceDirection: 'none', roundness: 0.5 },
    font: { color: '#475569', size: 9, face: 'Inter' },
    arrows: { to: { enabled: true, scaleFactor: 0.5 } }
  },
  physics: {
    enabled: true,
    solver: 'barnesHut',
    barnesHut: { gravitationalConstant: -4000, centralGravity: 0.3, springLength: 95 },
    stabilization: { iterations: 150 }
  },
  background: { color: 'transparent' },
  interaction: { hover: true, tooltipDelay: 200, navigationButtons: false, keyboard: false }
};
```

**Graph panel additional elements:**
- Title: "Memory Graph" in Syne 700
- Small node legend below the graph: four colored dots with labels (User / Domain / Intent / Preference / Context)
- Stats row: "Domains: N | Intents: N | Sessions: N"
- "Reset Context" button (ghost, small): calls PATCH /context/{user_id} to clear and redraws graph with empty state
- "Add Note" button: opens a small inline textarea to type personalization_notes, saves on blur via PATCH /context

**Graph refresh trigger:** Call `GET /context/{user_id}` and rebuild graph after:
- Page load
- Every successful enhancement (in the "done" event handler)
- Every successful refine
- After "Add Note" saves

New nodes added after an enhancement should animate in (vis-network handles this via physics stabilization — just reinitialize the DataSet).

---

### History Bar (bottom, full width)

Horizontal scroll bar, 80px tall, shows last 7 enhancements from localStorage.

Each card (min-width 200px):
- Domain badge (colored pill)
- Intent text (muted, 11px)
- First 40 chars of enhanced prompt (monospace, ellipsis overflow)
- Quality score mini-bar
- Timestamp relative (e.g., "2m ago")

Click a card: repopulate the input textarea with the original prompt, set the output to show that enhancement result again.

---

### JavaScript Architecture

```javascript
// ── State ──────────────────────────────────────────────────────
const state = {
  userId: 'demo-user',
  targetAi: null,
  currentResult: null,
  currentSegments: [],
  sessionStats: { count: 0, totalQuality: 0, domains: [] },
  history: JSON.parse(localStorage.getItem('tv_history') || '[]'),
  network: null  // vis-network instance
};

// ── Core Functions ─────────────────────────────────────────────

async function streamEnhancement(prompt, targetAi, userId) {
  // Use fetch + ReadableStream (NOT EventSource — that's GET only)
  // Set button to loading state
  // Clear previous output
  // Open fetch with { method: 'POST', body: JSON.stringify({prompt, target_ai, user_id}) }
  // Stream response.body through a TextDecoder + line buffer
  // Parse SSE manually: split on \n\n, extract data: {...} lines, JSON.parse each
  // On type==='chunk': append content to streaming text display in annotated panel
  // On type==='done': 
  //   → store result in state.currentResult
  //   → call renderAnnotatedOutput(result)
  //   → call renderMetadata(result)
  //   → if result.clarification_questions.length > 0: showRefinePanel()
  //   → call addToHistory(prompt, result)
  //   → call refreshContextGraph(userId)
  //   → update session stats
  // On type==='error': showToast(message, 'error')
}

async function refinePrompt() {
  // Collect Q&A from refine panel inputs
  // POST /refine with {original_prompt, clarification_qa, user_id, target_ai}
  // On success: renderRefinedOutput(result) in refine section
  // On success: refreshContextGraph(userId)
}

function renderAnnotatedOutput(result) {
  // Build the annotated segments HTML
  // Each segment: <span class="segment" data-technique="..." data-color="..." data-reason="...">
  //   with inline style for bg color (15% opacity) and left border (100% opacity)
  // Attach hover handlers for tooltip
  // Attach click handlers for inline editing
}

function showTooltip(event, segment) {
  // Position and show floating card with technique label + reason
  // Hide on mouseleave
}

function makeSegmentEditable(segmentEl, segmentData) {
  // Replace span with contenteditable div
  // On blur or ✓ Done: update state.currentSegments, reassemble enhanced_prompt, toast
}

function renderMetadata(result) {
  // Update framework badge, intent/domain badges, quality bar
  // Update pe_techniques legend
  // Update summary text
}

function showRefinePanel(questions) {
  // Animate in the refine section
  // Render each question with its input field
}

async function refreshContextGraph(userId) {
  // GET /context/{userId}
  // Call buildGraphData(context)
  // If state.network exists: update DataSets
  // Else: create new vis.Network(container, data, options)
  // Update stats row
}

function addToHistory(originalPrompt, result) {
  const entry = {
    id: Date.now(),
    original: originalPrompt,
    result,
    timestamp: new Date().toISOString()
  };
  state.history.unshift(entry);
  state.history = state.history.slice(0, 7);
  localStorage.setItem('tv_history', JSON.stringify(state.history));
  renderHistoryBar();
}

function renderHistoryBar() {
  // Render history cards in the bottom bar
  // Each card is clickable to restore that enhancement
}

// Toast system
function showToast(message, type = 'success') {
  // Create toast div, position top-right
  // Animate in, auto-dismiss after 3000ms
  // Types: success (green), error (red), info (indigo)
}

// Copy helpers
async function copyToClipboard(text, label) {
  await navigator.clipboard.writeText(text);
  showToast(`${label} copied`, 'success');
}

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
  // Load userId from localStorage or default to 'demo-user'
  // Initialize empty vis-network graph
  // Load history from localStorage, render history bar
  // Fetch initial context for default user, render graph
  // Attach all event listeners
  // Animate page in (opacity 0 → 1)
});
```

---

### CSS Key Decisions

```css
/* Segment hover and edit state */
.segment {
  border-radius: 3px;
  padding: 1px 3px;
  border-left: 3px solid var(--segment-color);
  background: rgba(var(--segment-rgb), 0.12);
  cursor: pointer;
  transition: background 0.15s;
  font-family: 'DM Mono', monospace;
  line-height: 1.8;
}
.segment:hover { background: rgba(var(--segment-rgb), 0.22); }
.segment.editing {
  outline: 1px solid var(--segment-color);
  background: rgba(var(--segment-rgb), 0.25);
}

/* Floating tooltip card */
.segment-tooltip {
  position: fixed;
  background: #0f0f1a;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  padding: 10px 14px;
  max-width: 280px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.6);
  z-index: 1000;
  pointer-events: none;
}

/* vis-network container must have explicit height */
#context-graph {
  width: 100%;
  height: calc(100vh - 200px);
  background: transparent;
  border-radius: 8px;
}

/* Quality bar */
.quality-bar-fill {
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(90deg, #f43f5e, #f59e0b, #10b981);
  background-size: 200% 100%;
  background-position: calc(100% - var(--score) * 100%) 0;
  transition: width 0.6s ease;
}

/* Framework badge */
.framework-badge {
  font-family: 'Syne', sans-serif;
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.4);
  color: #818cf8;
  cursor: help;
}

/* Streaming cursor */
.streaming-cursor::after {
  content: '▋';
  animation: blink 0.8s step-end infinite;
  color: #6366f1;
}
@keyframes blink { 50% { opacity: 0; } }
```

---

## Updated API Response Handling

Update `api/enhance.py` — the `done` event's `result` field must include the full new JSON structure. The LLM returns it via JSON mode, so parse and forward as-is.

Update `storage/store.py` — `update_after_enhancement` should also save the `framework_used` from the result:
```python
def update_after_enhancement(user_id, intent, domain, summary, framework=None):
    # existing logic +
    # track framework usage in a frameworks_used list (deduplicated)
```

---

## Verification Additions (add to original checklist)

- [ ] `POST /enhance` result includes `annotated_segments` array with valid technique keys
- [ ] Each segment's `text` concatenates to equal `enhanced_prompt`
- [ ] Annotated view renders colored segments with visible technique differentiation
- [ ] Hovering a segment shows tooltip with technique label + reason
- [ ] Clicking a segment makes it inline-editable
- [ ] "Copy Plain" copies the plain `enhanced_prompt` string
- [ ] After copying, "Copy" button shows "Copied!" for 2s then resets
- [ ] vis-network graph renders with at least the User center node on load
- [ ] After first enhancement, new domain and intent nodes appear in graph
- [ ] Hovering a graph node shows a tooltip with node details
- [ ] Framework badge shows correct framework with rationale on hover
- [ ] pe_techniques legend shows only techniques actually present in segments
- [ ] Refine panel renders when clarification_questions.length > 0
- [ ] Refined output also renders with annotated segments view
- [ ] History bar shows cards after enhancements, click restores state
- [ ] "Add Note" in graph panel saves to user context and graph refreshes
