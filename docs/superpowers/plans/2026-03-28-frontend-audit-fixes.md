# Frontend Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all issues identified in the comprehensive frontend audit: remove console statements, fix accessibility violations, complete light theme, normalize hard-coded colors.

**Architecture:** 5 independent tasks targeting specific issue categories. Each task produces a working build with no regressions. Tasks ordered by impact: console cleanup (quick win) -> a11y fixes -> light theme completion -> color normalization -> performance polish.

**Tech Stack:** Angular 21, SCSS, CoreUI, TypeScript strict mode.

---

## File Structure

### Task 1 — Console Cleanup (45 files touched)
All `.ts` files in `views/`, `shared/`, `core/` with console statements.

### Task 2 — Accessibility Fixes (6 files)
- `shared/components/signal-audit-drawer/signal-audit-drawer.component.html`
- `views/dashboard/dashboard.component.html`
- `views/ai-models/ai-models.component.ts` (modal + tab anchors)
- `views/paper-trading/paper-trading.component.ts` (modal)
- `views/trade-journal/trade-journal.component.ts` (modals)

### Task 3 — Light Theme Completion (1 file)
- `frontend/src/scss/_light-theme.scss`

### Task 4 — Hard-coded Color Normalization (10+ files)
- Component `.ts` files with inline hex/rgba values
- `frontend/src/scss/_custom.scss`

### Task 5 — Performance Polish (5 files)
- Large inline template extraction (paper-trading, backtest, trade-journal)
- Smart polling improvements

---

## Task 1: Console Statement Cleanup

Remove all `console.log/warn/error` from production code. Keep `console.error` ONLY in interceptors and guards (legitimate error boundaries). Replace with nothing — Angular services already handle errors via toast/signal.

**Files (grouped by action):**

**DELETE entirely (debug-only statements):**
- `views/base/list-groups/list-groups.component.ts:55` — `console.log(this.checkBoxes.value)`
- `views/forms/validation/validation.component.ts:40,45,50,55,60,65` — 6x `console.log('Submit/Reset...')`
- `views/notifications/toasters/toasters.component.ts:104` — `console.log('onVisibleChange')`
- `views/widgets/widgets-dropdown/widgets-dropdown.component.ts:240,257` — `console.log('before/after')`

**DELETE (error handling already in service/toast):**
- `views/markets/markets.component.ts:268,283` — polling errors (silently retry)
- `views/paper-trading/paper-trading.component.ts:884,899` — polling errors
- `views/dashboard/dashboard.component.ts:247,262` — polling errors
- `views/pages/register/register.component.ts:163` — registration error
- `views/pages/login/login.component.ts:78` — login error
- `views/user-profile/user-profile.component.ts:75,125` — profile errors
- `shared/components/avatar-upload/avatar-upload.component.ts:267` — upload error
- `shared/components/avatar/avatar.component.ts:133` — avatar load warning
- `shared/components/epic-logo/epic-logo.component.ts:125` — logo load warning
- `core/services/auth.service.ts:82,108,124,172,219,287,311` — 7x auth errors
- `core/services/news.service.ts:54,81,103` — 3x news errors
- `core/services/monitoring.service.ts:163,191,219,247` — 4x monitoring errors
- `core/services/market-status.service.ts:62` — market status error
- `core/services/logo.service.ts:196,211` — cache errors

**KEEP (legitimate error boundaries):**
- `core/interceptors/error.interceptor.ts:58` — KEEP (global API error logging)
- `core/guards/auth.guard.ts:18` — KEEP (security logging)
- `core/guards/permission.guard.ts:17,27,38,73,104` — KEEP (security logging)
- `core/interceptors/auth.interceptor.ts:35` — KEEP (403 logging)

- [ ] **Step 1: Remove all debug console.log statements**

Delete the `console.log` lines from:
- `views/base/list-groups/list-groups.component.ts:55`
- `views/forms/validation/validation.component.ts:40,45,50,55,60,65`
- `views/notifications/toasters/toasters.component.ts:104`
- `views/widgets/widgets-dropdown/widgets-dropdown.component.ts:240,257`

- [ ] **Step 2: Remove console.error/warn from components (errors handled elsewhere)**

For each file, delete the `console.error(...)` or `console.warn(...)` line. The error is already handled by the `.subscribe({ error: () => {} })` pattern or toast service.

Files: markets, paper-trading, dashboard, register, login, user-profile, avatar-upload, avatar, epic-logo.

- [ ] **Step 3: Remove console statements from core services**

Files: auth.service.ts (7 statements), news.service.ts (3), monitoring.service.ts (4), market-status.service.ts (1), logo.service.ts (2).

- [ ] **Step 4: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove 45+ console statements from production code

Keep console.error only in error.interceptor and auth/permission guards
(legitimate error boundaries). All other error handling done via
toast service or signal error callbacks."
```

---

## Task 2: Accessibility Fixes

Fix the 2 non-semantic click handlers + 4 modals without ARIA + tab navigation.

- [ ] **Step 1: Fix signal-audit-drawer backdrop**

File: `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.html:3`

```html
<!-- BEFORE -->
<div class="audit-backdrop" (click)="onBackdropClick()"></div>

<!-- AFTER -->
<div class="audit-backdrop" (click)="onBackdropClick()" role="button" tabindex="-1" aria-label="Chiudi pannello"></div>
```

Note: `tabindex="-1"` (not `0`) because backdrop should be clickable but not in tab order — ESC key already handles keyboard close.

- [ ] **Step 2: Fix dashboard clickable table row**

File: `frontend/src/app/views/dashboard/dashboard.component.html:478`

```html
<!-- BEFORE -->
<tr (click)="auditService.openByDealId(pos.deal_id, pos.epic)" style="cursor:pointer;">

<!-- AFTER -->
<tr (click)="auditService.openByDealId(pos.deal_id, pos.epic)"
    (keydown.enter)="auditService.openByDealId(pos.deal_id, pos.epic)"
    tabindex="0" role="row" style="cursor:pointer;">
```

- [ ] **Step 3: Fix modal ARIA in ai-models**

File: `frontend/src/app/views/ai-models/ai-models.component.ts`

Find the news modal backdrop div and add:
```html
<div class="am-modal-backdrop" (click)="closeNewsModal()" role="dialog" aria-modal="true" aria-label="News">
```

Fix tab anchors — replace `<a ... style="cursor:pointer">` with proper button or add `role="tab"`.

- [ ] **Step 4: Fix modal ARIA in paper-trading and trade-journal**

Same pattern: add `role="dialog"` `aria-modal="true"` `aria-label` to modal backdrops.

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(a11y): add ARIA attributes to modals, keyboard support to clickable rows"
```

---

## Task 3: Light Theme Completion

Add missing light theme overrides for 15+ component styles that currently only work in dark mode.

- [ ] **Step 1: Add signal-status light overrides**

File: `frontend/src/scss/_light-theme.scss`

```scss
// Signal status badges (dark mode uses neon colors that clash with white bg)
.signal-status {
  &--executed .signal-status__dot { background-color: #16a34a; }
  &--rejected .signal-status__dot { background-color: #dc2626; }
  &--exec_failed .signal-status__dot { background-color: #dc2626; }
  &--predicted .signal-status__dot { background-color: #2563eb; }
  &--hold .signal-status__dot { background-color: #6b7280; }
}
```

- [ ] **Step 2: Add regime-badge light overrides**

```scss
.regime-badge {
  &--trending_up { background: rgba(22, 163, 74, 0.1); color: #16a34a; }
  &--trending_down { background: rgba(220, 38, 38, 0.1); color: #dc2626; }
  &--ranging { background: rgba(37, 99, 235, 0.1); color: #2563eb; }
}
```

- [ ] **Step 3: Add risk-badge light overrides**

```scss
.risk-badge {
  &--local { background: rgba(245, 158, 11, 0.1); color: #d97706; border-color: rgba(245, 158, 11, 0.3); }
  &--broker { background: rgba(37, 99, 235, 0.1); color: #2563eb; border-color: rgba(37, 99, 235, 0.3); }
  &--none { background: rgba(220, 38, 38, 0.1); color: #dc2626; border-color: rgba(220, 38, 38, 0.3); }
}
```

- [ ] **Step 4: Add header-widget-slot and footer light overrides**

```scss
.header-widget-slot {
  background: rgba(0, 0, 0, 0.03);
  color: rgba(0, 0, 0, 0.65);
}
.footer-brand { color: rgba(0, 128, 80, 0.6); }
```

- [ ] **Step 5: Add SL cooldown badge and training job card light overrides**

```scss
.sl-cooldown-badge {
  &--warning { background: rgba(245, 158, 11, 0.1); color: #d97706; border-color: rgba(245, 158, 11, 0.3); }
  &--blocked { background: rgba(220, 38, 38, 0.1); color: #dc2626; border-color: rgba(220, 38, 38, 0.3); }
}
.training-job-card {
  &--queued { border-left-color: #9ca3af; }
  &--running { border-left-color: #0891b2; }
  &--completed { border-left-color: #16a34a; }
  &--failed { border-left-color: #dc2626; }
}
```

- [ ] **Step 6: Add table-danger light mode override**

```scss
// Light mode: table-danger needs dark text (Bootstrap default is fine for light)
.table-danger, .table > tbody > tr.table-danger {
  &:hover, &:hover td { background-color: rgba(220, 38, 38, 0.08) !important; }
}
```

- [ ] **Step 7: Verify build + visual check**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`

- [ ] **Step 8: Commit**

```bash
git commit -m "style: complete light theme — signal-status, regime, risk, cooldown, training badges"
```

---

## Task 4: Hard-coded Color Normalization

Replace hard-coded hex/rgba values with CSS variables in the most impactful component files. Prioritize files that affect trading UX (not demo/base components).

**Scope**: Focus on production components only. Skip demo/base CoreUI template components (charts.component.ts, carousels, etc.).

- [ ] **Step 1: Normalize news-widget sentiment colors**

File: `frontend/src/app/shared/components/news-widget/news-widget.component.ts`

Replace 7 hard-coded sentiment colors with CSS classes:
```typescript
// BEFORE: sentimentColor = '#28a745'
// AFTER: sentimentClass = 'sentiment--very-positive'
```

Add to `_custom.scss`:
```scss
.sentiment--very-positive { color: var(--mantis-profit); }
.sentiment--positive { color: var(--mantis-green); }
.sentiment--slightly-positive { color: var(--mantis-green); opacity: 0.7; }
.sentiment--neutral { color: var(--mantis-neutral); }
.sentiment--slightly-negative { color: var(--mantis-warning); }
.sentiment--negative { color: var(--mantis-loss); opacity: 0.7; }
.sentiment--very-negative { color: var(--mantis-loss); }
```

- [ ] **Step 2: Normalize avatar-upload colors**

File: `frontend/src/app/shared/components/avatar-upload/avatar-upload.component.ts`

Replace 8 instances of `#39FF14`, `rgba(57, 255, 20, ...)`, `rgba(22, 27, 34, ...)` with `var(--mantis-neon)`, `var(--mantis-surface-2)`.

- [ ] **Step 3: Normalize news.component colors**

File: `frontend/src/app/views/news/news.component.ts`

Replace `#00d97e`, `#ef5350`, `#adb5bd` with CSS classes using design tokens.

- [ ] **Step 4: Normalize signal-status colors in _custom.scss**

File: `frontend/src/scss/_custom.scss`

Replace hard-coded hex in `.signal-status` variants:
```scss
// BEFORE: color: #ef5350;
// AFTER: color: var(--mantis-loss);
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`

- [ ] **Step 6: Commit**

```bash
git commit -m "style: normalize 30+ hard-coded colors to design tokens"
```

---

## Task 5: Performance Polish

Remove the biggest performance concerns: smart polling and template size awareness.

- [ ] **Step 1: Add market-hours-aware polling to dashboard**

File: `frontend/src/app/views/dashboard/dashboard.component.ts`

Instead of fixed 10s polling, pause or slow down when market is closed:
```typescript
// In startPolling:
const interval = this.isMarketOpen() ? 10_000 : 60_000;
```

This requires reading the market status signal already available in the component.

- [ ] **Step 2: Add market-hours-aware polling to positions**

Same pattern in `frontend/src/app/views/positions/positions.component.ts`.

- [ ] **Step 3: Add market-hours-aware polling to paper-trading**

Same pattern in `frontend/src/app/views/paper-trading/paper-trading.component.ts`.

- [ ] **Step 4: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`

- [ ] **Step 5: Commit**

```bash
git commit -m "perf: slow polling to 60s when market closed (was fixed 10s)"
```

---

## Verification

After all 5 tasks:

- [ ] **Full frontend build**: `cd frontend && npx ng build --configuration=development`
- [ ] **Visual check dark mode**: Navigate all pages, verify no regressions
- [ ] **Visual check light mode**: Toggle theme, verify new light overrides
- [ ] **Grep console**: `grep -r "console\." frontend/src/app/ --include="*.ts" | grep -v spec | grep -v node_modules | grep -v guard | grep -v interceptor`
- [ ] **Final commit + push**

```bash
git push origin master
```
