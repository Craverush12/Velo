# Velocity Sidebar Extension — Execution Plan

**Audience:** Product, design, engineering, leadership  
**Product:** ThinkVelocity Chrome side panel + on-page enhance experience  
**Detailed QA checklist (engineering):** [`CHANGES.md`](./CHANGES.md)  
**Visual / light theme plan:** [`DESIGN_EXECUTION.md`](./DESIGN_EXECUTION.md)

---

## What we are building

A Chrome extension that helps users **improve prompts** in a side panel, then **use the result** on ChatGPT, Claude, Gemini, and similar sites. Most of the side panel is **done**. Next major work: the **floating button and popup on AI websites** (same idea as the main Velocity extension today).

---

## Status at a glance

| Phase | Name | Status |
|-------|------|--------|
| **0** | Sign-in & foundation | **Done** |
| **1** | Enhance session (core flow) | **Done** |
| **2** | Output actions (Insert, Open In, Refine) | **Done** |
| **3** | Plans, usage limits & Pro styling | **Done** |
| **4** | Prompt library, collections, memories | **Done** |
| **5** | Polish & release readiness | **In progress** |
| **6** | On-page button & enhance popup | **Not started** |
| **7** | Light theme (all surfaces) | **Not started** — see [Design plan](./DESIGN_EXECUTION.md) |

**Legend:** Done · In progress · Not started

---

## Phase 0 — Sign-in & foundation

**Goal:** User can open the side panel, sign in with ThinkVelocity, and stay signed in.

**Status:** Done

**Main tasks**
1. Open side panel from the extension icon  
2. Sign in via ThinkVelocity website; account syncs to the extension  
3. Show login screen when signed out (not a broken home screen)  
4. Support consumer vs enterprise entry (routing after login)  
5. Open profile and key website pages from the side rail  

---

## Phase 1 — Enhance session (core flow)

**Goal:** User writes a prompt, sees Velocity “think,” then gets a clear enhanced result in the panel.

**Status:** Done

**Main tasks**
1. User submits a prompt from the bottom composer  
2. Show **thought process** while the prompt is being enhanced  
3. Show **Output** with original prompt (collapsible) and enhanced result (structured sections and lists)  
4. **Suggestions** tab for follow-up questions and refine flow  
5. **Versions** tab for original, enhanced, and refined history  
6. Clear composer after enhance; mic/send behave correctly in session  

---

## Phase 2 — Output actions

**Goal:** User can act on the enhanced prompt without retyping.

**Status:** Done

**Main tasks**
1. **Insert in Chat** — puts formatted text into the **active browser tab** (e.g. ChatGPT); falls back to side panel composer if that tab is not a supported chat site  
2. **Refine** — moves user to Suggestions to improve the prompt further  
3. **Open In** — opens chosen AI site (ChatGPT, Claude, Gemini, etc.) with the prompt filled in  
4. Copy, edit, and feedback (thumbs) on the enhanced card  
5. **Pro Enhanced** label and gold styling for Pro users on the result card  

---

## Phase 3 — Plans, usage limits & Pro styling

**Goal:** Free and Pro users see fair limits; Pro feels premium without breaking the main cyan look.

**Status:** Done

**Main tasks**
1. Show how many enhances are left; block enhance when limit is reached  
2. Banner when usage is low or exhausted  
3. Pro vs Free visual treatment (gold where it matters; tabs and filters stay cyan)  
4. Pro-only library content and paywall where required  

---

## Phase 4 — Prompt library, collections & memories

**Goal:** User can browse, save, and reuse prompts inside the extension.

**Status:** Done

**Main tasks**
1. **Prompt library** in the panel (browse, detail, copy)  
2. **Collections** and **memories** lists with create/edit flows  
3. **Prompt book** of past enhanced prompts  
4. Open in chat from library without breaking navigation or login state  

---

## Phase 5 — Polish & release readiness

**Goal:** Stable, shippable experience with clear errors and quality checks.

**Status:** In progress

**Main tasks**
1. Clear user messages when insert or open-in fails (not only silent errors)  
2. Save/bookmark on enhanced card (if in scope for v1)  
3. Final testing on staging and production accounts (Free, Pro trial, Pro paid)  
4. Version bump and release checklist  
5. Optional: analytics parity with main extension  

---

## Phase 6 — On-page button & enhance popup

**Goal:** On ChatGPT, Claude, Gemini, and other supported sites, user sees Velocity **next to the chat box**, clicks to enhance in a **small popup**, and accepts the result into that page — without opening the side panel first.

**Status:** Not started  
**Reference experience:** Current main Velocity extension (Extension-new)

**Main tasks**

1. **Show the Velocity button** when the user types in a supported site’s chat box (hide when empty or when popup is open).  

2. **Enhance prompt button** opens a popup with loading state, then the **enhanced text** (readable sections and lists, like the Output tab).  

3. **Draggable popup** — user can move it by the header; position is remembered during the session.  

4. **Actions in the popup** — Copy, **Accept** (insert into that page’s chat box), optional link to open the **side panel** for deeper refine.  

5. **Usage & sign-in** — respect plan limits; button reflects Free / Pro; snooze and basic menu (pin, profile) aligned with main extension where needed.  

6. **Works on major platforms** — at minimum ChatGPT, Claude, and Gemini; expand to the same list as the main extension over time.  

**Done when:** A user on ChatGPT can type, click Velocity, see enhanced text in the popup, drag it, and Accept to fill the chat input — same mental model as Extension-new.

---

## Phase 7 — Light theme

**Goal:** Default look is **light and clean** across side panel, on-page button, and popup — one Velocity brand (cyan + Pro gold).

**Status:** Not started  

**Owner:** Design-led; engineering implements tokens and styles.  

**See:** [`DESIGN_EXECUTION.md`](./DESIGN_EXECUTION.md) for screen-by-screen design tasks (no code detail).

---

## How teams use this doc

| Team | Use this for |
|------|----------------|
| **Leadership / PM** | Phase status and what’s left before launch |
| **Design** | Phase 7 + [`DESIGN_EXECUTION.md`](./DESIGN_EXECUTION.md) |
| **Engineering** | Phase scope here; implementation detail in [`CHANGES.md`](./CHANGES.md) |

---

*Last updated: May 2026*
