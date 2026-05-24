# Velocity Enterprise Extension — Goal Checklist

End-user facing. Every item here should be true before Phase 1 ships.

---

## Auth

- [ ] A user seeing the extension for the first time can tap "Enterprise Login" on the welcome screen
- [ ] The enterprise login form appears inside the side panel — no redirect to a browser tab
- [ ] A user can log in with their work email and password
- [ ] A wrong password shows a clear error message inline
- [ ] After login, the panel immediately shows the enterprise workspace (not the consumer view)
- [ ] "Forgot password?" opens the enterprise web portal in a new tab
- [ ] A logged-in enterprise user can log out from the panel header
- [ ] After logout the panel returns to the enterprise login form (not the consumer view)
- [ ] If the session expires silently, the user sees "Session expired — please log in again" and is taken back to the login form
- [ ] A user who also has a consumer account can switch between consumer and enterprise mode without logging out of either

---

## Enhance (Enterprise)

- [ ] Pressing the enhance button in enterprise mode sends the prompt through a company policy check first
- [ ] If the prompt is clean, enhancement proceeds instantly with no extra steps
- [ ] If the prompt is flagged with a warning, the user sees the reason and can choose to proceed or cancel
- [ ] If the prompt requires confirmation, the user sees a modal and must explicitly confirm before it enhances
- [ ] If the prompt contains sensitive content that was removed (redacted), the user sees the cleaned version and can choose to enhance with it or cancel
- [ ] If the prompt is blocked by company policy, the user sees a clear "blocked" message with the reason — no enhancement happens
- [ ] If the prompt requires admin approval, the user sees a "Sent for admin review" message — no enhancement happens until approved
- [ ] After closing and reopening the panel, a pending admin review is still visible as a banner
- [ ] Enhanced output streams in the same way as consumer mode — no janky loading states

---

## Mode Experience

- [ ] The enterprise panel looks and feels distinct from the consumer panel (branding, header)
- [ ] Switching from enterprise to consumer mode is one click and takes effect instantly
- [ ] Switching modes does not log the user out of either account
- [ ] The active mode is remembered across browser restarts

---

## Edge Cases

- [ ] Opening the panel on a new device/profile with no stored session lands on the login form, not a broken state
- [ ] Network failure during guardrail check shows a friendly error and lets the user retry
- [ ] Network failure during enhancement (after guardrail pass) shows a friendly error and lets the user retry
- [ ] The extension does not break consumer mode for users who never touch enterprise

---

## Phase 2 (not in scope now — listed to stay aligned)

- [ ] Context Packs — org-uploaded documents appear as context when enhancing
- [ ] Prompt Collections — org-shared prompt library browsable inside the panel
- [ ] Team switcher — user can switch active team context
- [ ] Prompt audit trail — user can see history of their enterprise prompts and their moderation outcomes
- [ ] Analytics — admin can see usage stats (this is a web frontend feature, not extension)
