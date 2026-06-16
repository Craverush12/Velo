# Velocity Extension — Design Execution Plan (Light Theme)

**Audience:** Design, product, engineering, leadership  
**Goal:** One consistent **light** Velocity look everywhere users see the product  
**Build plan (features):** [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md)

---

## Design direction

| Topic | Direction |
|-------|-----------|
| **Default look** | Light backgrounds, dark readable text |
| **Brand color** | Cyan — primary buttons, borders, active states |
| **Pro / trial** | Gold accents on labels and Pro cards (not replacing cyan everywhere) |
| **Feel** | Clean, modern, similar to ThinkVelocity web — not a dark-only extension |

Side panel session tabs (Output, Suggestions, etc.) **stay cyan** so the active flow is easy to follow. Gold is for **Pro** moments (enhanced result card, profile, Pro button ring).

---

## Status at a glance

| Area | Status |
|------|--------|
| Shared color & type rules | Not started |
| Side panel (main UI) | Not started |
| On-page **Enhance** button | Not started |
| Enhancement **popup** | Not started |
| Cross-screen consistency review | Not started |

---

## 1. Shared brand rules (all screens)

**Main tasks**

1. Define one **light palette**: page background, card white, secondary grey, text primary/secondary, cyan, Pro gold.  
2. Default theme = **light** for new users (dark optional later).  
3. Same font family across panel, button, and popup.  
4. Same corner style: rounded pills for buttons, rounded cards for panels.  
5. Pro gold only where we mean “premium” — not on every label.

**Design deliverable:** Simple token sheet (colors + type scale) the team can share in Figma.

---

## 2. Side panel — main page

**What users see:** Login, home, enhance session (tabs + composer), library, collections, memories.

**Status:** Today the panel is **dark**; this phase moves it to **light**.

**Main tasks**

1. **Shell** — light grey page background, white content cards, clear side rail icons.  
2. **Login & home** — welcome and prompt cards readable on light; cyan primary buttons.  
3. **Composer** — white input area, subtle border, cyan send/mic; mode and attach menus as white floating panels.  
4. **Output tab** — match approved mockups: original strip, enhanced card (white + Pro gold border when Pro), **Insert in Chat** and **Refine / Open In** pills below.  
5. **Other tabs** — Suggestions, Versions, Context, thought-process loader: light cards, cyan accents only where active.  
6. **Library & modals** — grid cards, detail overlay, Pro paywall: all designed for light backgrounds.  
7. **Usage banner** — visible warning style on light (not only dark-mode colors).

**Done when:** Full panel walkthrough in Figma (or staging) looks intentional in light mode, signed off by design + product.

---

## 3. On-page Enhance button

**What users see:** Small **“Enhance prompt”** control near the chat input on ChatGPT, Claude, etc. (Phase 6 feature).

**Main tasks**

1. **Default state** — white pill, cyan outline, dark “Enhance prompt” label and icon.  
2. **Hover** — clear feedback (e.g. dark fill on left segment) without looking like a different product.  
3. **Dropdown menu** — white menu, cyan border, readable mode list; Pin / Snooze / Profile icons for light background.  
4. **Pro user** — subtle gold ring on the button (optional).  
5. **Disabled / limit reached** — greyed, clear “limit reached” tooltip.  
6. **Placement** — specs for spacing above/near chat input so it doesn’t cover send buttons (per platform notes from product).

**Design deliverable:** Button + menu specs on light ChatGPT and one other site (e.g. Claude).

---

## 4. Enhancement popup

**What users see:** Floating window after clicking Enhance — loading, then enhanced text, then Copy / Accept.

**Main tasks**

1. **Container** — light grey/white popup, soft shadow, rounded corners (~18px).  
2. **Header** — draggable area, plan label (Free / Pro), **Panel** and **Close**; Pro title in gold when applicable.  
3. **Tabs** — Enhance (active cyan) and Refine (disabled or locked for Free on light).  
4. **Content** — loading skeleton on light; enhanced text readable (sections, bullets, spacing like Output tab).  
5. **Footer actions** — Like / Dislike / Copy / **Accept** (cyan primary); spacing and touch targets for desktop.  
6. **Empty & error** — friendly messages on light (rate limit, no text, etc.).  
7. **Drag** — cursor and slight feedback while moving; popup stays inside the screen.

**Design deliverable:** Popup states: loading, success, error, rate-limited, Pro — all on light.

---

## 5. Final design QA (all surfaces)

**Main tasks**

1. Cyan matches across panel, button, popup, and marketing site.  
2. Pro gold matches across enhanced card, popup header, Pro button.  
3. Insert / Open In / Accept flows look correct on light **and** on real ChatGPT white UI.  
4. Text contrast check (body copy readable on every background).  
5. Sign-off: Design + Product + one engineering rep.

---

## Suggested order

1. Shared brand rules (Section 1)  
2. Side panel light (Section 2) — can ship before Phase 6  
3. Button + popup (Sections 3–4) — with Phase 6 build  
4. Final QA (Section 5)

---

## Related documents

| Document | Purpose |
|----------|---------|
| [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md) | Feature phases 0–7 (what we build) |
| [`CHANGES.md`](./CHANGES.md) | Engineering checklist & test steps |

---

*Last updated: May 2026 — stakeholder-friendly design plan; light theme default.*
