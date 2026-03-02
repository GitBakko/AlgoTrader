# MANTIS AI — Full Visual Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Elevate MANTIS AI from 7.8/10 to 9+/10 visual quality across all pages via 6 design layers: normalize, polish, animate, colorize, bolder, delight.

**Architecture:** Layer-by-layer approach. Create `_motion.scss` for all new keyframes/animations. Add utility classes in `_custom.scss`. Modify component templates for class application. All animations respect `prefers-reduced-motion`.

**Tech Stack:** SCSS (Angular 21 + CoreUI), CSS custom properties, CSS keyframe animations, Angular Signals for dynamic class binding.

---

## Task 1: Create `_motion.scss` with animation keyframes and utilities

**Files:**
- Create: `frontend/src/scss/_motion.scss`
- Modify: `frontend/src/scss/styles.scss` (add import)

**Step 1: Create `_motion.scss`**

Create `frontend/src/scss/_motion.scss` with ALL new keyframes and utility classes:

```scss
// ============================================================
// MANTIS AI — Motion & Animation System
// ============================================================
@use "palette" as *;

// ── Easing ──
$ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
$ease-out-back: cubic-bezier(0.34, 1.56, 0.64, 1);

// ── Keyframes ──

@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes valueFlash {
  0%   { background-color: transparent; }
  30%  { background-color: rgba($mantis-green, 0.12); }
  100% { background-color: transparent; }
}

@keyframes valueFlashRed {
  0%   { background-color: transparent; }
  30%  { background-color: rgba($mantis-loss, 0.10); }
  100% { background-color: transparent; }
}

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

@keyframes bellShake {
  0%   { transform: rotate(0); }
  15%  { transform: rotate(12deg); }
  30%  { transform: rotate(-10deg); }
  45%  { transform: rotate(6deg); }
  60%  { transform: rotate(-3deg); }
  75%  { transform: rotate(1deg); }
  100% { transform: rotate(0); }
}

@keyframes glowPulse {
  0%, 100% { box-shadow: 0 0 4px rgba($mantis-neon, 0.15); }
  50%      { box-shadow: 0 0 12px rgba($mantis-neon, 0.35); }
}

@keyframes sectionShimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

@keyframes emergencyPulse {
  0%, 100% { box-shadow: 0 0 6px rgba($mantis-loss, 0.3); }
  50%      { box-shadow: 0 0 16px rgba($mantis-loss, 0.5); }
}

// ── Utility Classes ──

@media (prefers-reduced-motion: no-preference) {
  .animate-in {
    animation: fadeSlideUp 0.4s $ease-out-expo both;
  }

  .fade-in {
    animation: fadeIn 0.25s ease-out both;
  }

  // Stagger delays for grids/lists
  .stagger-1 { animation-delay: 50ms; }
  .stagger-2 { animation-delay: 100ms; }
  .stagger-3 { animation-delay: 150ms; }
  .stagger-4 { animation-delay: 200ms; }
  .stagger-5 { animation-delay: 250ms; }
  .stagger-6 { animation-delay: 300ms; }

  .value-flash {
    animation: valueFlash 0.6s ease-out;
  }

  .value-flash-red {
    animation: valueFlashRed 0.6s ease-out;
  }

  .skeleton-shimmer {
    background: linear-gradient(
      90deg,
      var(--mantis-surface-2) 25%,
      var(--mantis-surface-3) 50%,
      var(--mantis-surface-2) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
  }

  .bell-shake {
    animation: bellShake 0.5s $ease-out-back;
  }

  .glow-pulse {
    animation: glowPulse 3s ease-in-out infinite;
  }

  .emergency-glow {
    animation: emergencyPulse 2s ease-in-out infinite;
  }
}
```

**Step 2: Add import to `styles.scss`**

In `frontend/src/scss/styles.scss`, add the motion import AFTER `"custom"` and BEFORE `"light-theme"`:

```scss
// Brand-specific customizations
@use "custom";

// Motion & animations
@use "motion";

// Light theme overrides
@use "light-theme";
```

**Step 3: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: Build succeeds with 0 errors.

**Step 4: Commit**

```bash
git add frontend/src/scss/_motion.scss frontend/src/scss/styles.scss
git commit -m "ui: add motion system with keyframes and animation utilities"
```

---

## Task 2: Layer 1 — Normalize (global consistency)

**Files:**
- Modify: `frontend/src/scss/_custom.scss`
- Modify: `frontend/src/app/views/signals/signals.component.ts` (inline template + class)
- Modify: `frontend/src/app/views/signals/signals.component.scss`

**Step 1: Increase confidence bar height globally**

In `frontend/src/scss/_custom.scss`, add after the existing `.conf-bar-wrapper` styles (or at end of global components section ~line 556):

```scss
// ── Confidence bar uniform height ──
.conf-bar-wrapper {
  height: 6px !important;

  .progress-bar {
    border-radius: 3px;
  }
}
```

Also in `frontend/src/app/views/signals/signals.component.scss`, change `.conf-progress` height from `4px` to `6px` (line 23).

**Step 2: Add KPI summary row to Signals page**

In `frontend/src/app/views/signals/signals.component.ts`, add computed signals in the class (after line ~117):

```typescript
readonly totalSignals = computed(() => this.signals().length);
readonly executedPct = computed(() => {
  const s = this.signals();
  if (!s.length) return 0;
  return Math.round((s.filter(x => x.status === 'executed').length / s.length) * 100);
});
readonly avgConfidence = computed(() => {
  const s = this.signals().filter(x => x.confidence > 0);
  if (!s.length) return 0;
  return Math.round((s.reduce((sum, x) => sum + x.confidence, 0) / s.length) * 100);
});
readonly topStrategy = computed(() => {
  const s = this.signals();
  if (!s.length) return '—';
  const counts: Record<string, number> = {};
  s.forEach(x => { counts[x.strategy_name || 'unknown'] = (counts[x.strategy_name || 'unknown'] || 0) + 1; });
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || '—';
});
```

In the inline template, add a KPI row BEFORE the table card (before the `@if (signals().length > 0)` block). Insert after the card-header closing tag (around line 35):

```html
<!-- KPI Summary Row -->
<c-row class="mb-3 g-3">
  <c-col xs="6" md="3">
    <c-card class="h-100 border-top border-top-3 border-top-primary">
      <c-card-body class="py-2 px-3">
        <div class="text-body-secondary small">Segnali Totali</div>
        <div class="mantis-kpi fs-5">{{ totalSignals() }}</div>
      </c-card-body>
    </c-card>
  </c-col>
  <c-col xs="6" md="3">
    <c-card class="h-100 border-top border-top-3 border-top-primary">
      <c-card-body class="py-2 px-3">
        <div class="text-body-secondary small">Eseguiti</div>
        <div class="mantis-kpi fs-5">{{ executedPct() }}%</div>
      </c-card-body>
    </c-card>
  </c-col>
  <c-col xs="6" md="3">
    <c-card class="h-100 border-top border-top-3 border-top-primary">
      <c-card-body class="py-2 px-3">
        <div class="text-body-secondary small">Confidenza Media</div>
        <div class="mantis-kpi fs-5">{{ avgConfidence() }}%</div>
      </c-card-body>
    </c-card>
  </c-col>
  <c-col xs="6" md="3">
    <c-card class="h-100 border-top border-top-3 border-top-primary">
      <c-card-body class="py-2 px-3">
        <div class="text-body-secondary small">Top Strategia</div>
        <div class="mantis-kpi fs-6">{{ topStrategy() }}</div>
      </c-card-body>
    </c-card>
  </c-col>
</c-row>
```

**Step 3: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 4: Commit**

```bash
git add frontend/src/scss/_custom.scss frontend/src/app/views/signals/
git commit -m "ui: normalize — signals KPI row + confidence bar 6px"
```

---

## Task 3: Layer 2 — Polish (spacing, hover, detail fixes)

**Files:**
- Modify: `frontend/src/scss/_custom.scss`
- Modify: `frontend/src/app/views/markets/markets.component.scss`
- Modify: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.scss`

**Step 1: Global table row hover**

In `frontend/src/scss/_custom.scss`, add in the global components section:

```scss
// ── Table row hover (universal) ──
[data-coreui-theme="dark"] {
  table tbody tr {
    transition: background-color 0.15s ease;

    &:hover {
      background-color: rgba(255, 255, 255, 0.03) !important;
    }
  }
}
```

**Step 2: Selected asset card enhancement (Markets)**

In `frontend/src/app/views/markets/markets.component.scss`, enhance the `.asset-card--selected` class (around line 19-22):

Replace the existing selected styles with:

```scss
  &--selected {
    border-left: 3px solid var(--mantis-green);
    background: rgba(0, 217, 126, 0.05);
    box-shadow: 0 0 12px rgba(0, 217, 126, 0.12);
  }
```

**Step 3: Notification bell unread pulse**

In `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.scss`, add after `.notification-badge` styles:

```scss
.notification-badge--pulse {
  animation: pulse-glow 2s ease-in-out infinite;
}
```

In the corresponding `.html` template, add the `notification-badge--pulse` class when `unreadCount() > 0` on the badge element.

**Step 4: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 5: Commit**

```bash
git add frontend/src/scss/_custom.scss frontend/src/app/views/markets/ frontend/src/app/layout/
git commit -m "ui: polish — table hover, selected card glow, bell pulse"
```

---

## Task 4: Layer 3 — Animate (entrance animations across all pages)

**Files:**
- Modify: `frontend/src/app/views/dashboard/dashboard.component.html`
- Modify: `frontend/src/app/views/signals/signals.component.ts` (inline template)
- Modify: `frontend/src/app/views/markets/markets.component.ts` (inline template)
- Modify: `frontend/src/app/views/positions/positions.component.html`
- Modify: `frontend/src/app/views/paper-trading/paper-trading.component.ts` (inline template)

**Step 1: Dashboard — staggered entrance on KPI cards and sections**

In `frontend/src/app/views/dashboard/dashboard.component.html`, add `animate-in stagger-N` classes to each KPI card `c-col`:

- 1st KPI card col: `class="... animate-in stagger-1"`
- 2nd KPI card col: `class="... animate-in stagger-2"`
- 3rd KPI card col: `class="... animate-in stagger-3"`
- 4th KPI card col: `class="... animate-in stagger-4"`

Add `animate-in` to each major section card (chart, positions summary, recent signals, performance).

**Step 2: Signals — animate KPI row and table**

In signals inline template, add `animate-in stagger-N` to each KPI c-col, and `animate-in` to the main table card.

**Step 3: Markets — animate asset cards**

In markets inline template, add `animate-in` class to the asset cards grid container.

**Step 4: Positions — animate tabs and table**

In `positions.component.html`, add `animate-in` to the main card container.

**Step 5: Paper Trading — animate risk management cards**

In paper-trading inline template, add `animate-in stagger-N` to the risk management KPI row cards.

**Step 6: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 7: Commit**

```bash
git add frontend/src/app/views/ frontend/src/app/layout/
git commit -m "ui: animate — entrance animations across all pages"
```

---

## Task 5: Layer 4 — Colorize (strategic color additions)

**Files:**
- Modify: `frontend/src/scss/_custom.scss`

**Step 1: Regime badge color tints**

In `frontend/src/scss/_custom.scss`, add:

```scss
// ── Regime badge tints ──
.regime-badge {
  &--trending_up {
    background: rgba(57, 255, 20, 0.10) !important;
    color: #39ff14 !important;
    border: 1px solid rgba(57, 255, 20, 0.20);
  }
  &--trending_down {
    background: rgba(255, 61, 87, 0.10) !important;
    color: #ff3d57 !important;
    border: 1px solid rgba(255, 61, 87, 0.20);
  }
  &--ranging {
    background: rgba(255, 176, 32, 0.10) !important;
    color: #ffb020 !important;
    border: 1px solid rgba(255, 176, 32, 0.20);
  }
}
```

**Step 2: 3-tier confidence bar color**

Add to `_custom.scss`:

```scss
// ── Confidence bar 3-tier color ──
.conf-bar-danger .progress-bar { background-color: var(--mantis-loss) !important; }
.conf-bar-warning .progress-bar { background-color: var(--mantis-warning) !important; }
.conf-bar-success .progress-bar { background-color: var(--mantis-profit) !important; }
```

Apply in component templates: use `[ngClass]` or computed class based on confidence value:
- `< 0.30` → `conf-bar-danger`
- `0.30-0.50` → `conf-bar-warning`
- `> 0.50` → `conf-bar-success`

**Step 3: P&L row tint**

Add to `_custom.scss`:

```scss
// ── P&L row tints ──
.pnl-row-positive {
  background: rgba(57, 255, 20, 0.03) !important;
}
.pnl-row-negative {
  background: rgba(255, 61, 87, 0.03) !important;
}
```

Apply in positions/paper-trading table rows via `[class]` binding based on P&L value.

**Step 4: Active nav glow enhancement**

Add to sidebar section of `_custom.scss`:

```scss
// ── Active nav glow ──
.sidebar-nav .nav-link.active {
  box-shadow: -2px 0 8px rgba(0, 217, 126, 0.15);
}
```

**Step 5: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 6: Commit**

```bash
git add frontend/src/scss/_custom.scss frontend/src/app/views/
git commit -m "ui: colorize — regime badges, confidence gradient, P&L tints, nav glow"
```

---

## Task 6: Layer 5 — Bolder (amplify flat designs)

**Files:**
- Modify: `frontend/src/scss/_custom.scss`
- Modify: `frontend/src/app/views/paper-trading/paper-trading.component.ts` (inline template, emergency stop)

**Step 1: Dashboard KPI left accent glow pulse**

In `_custom.scss`, add:

```scss
// ── KPI accent glow (hero card only) ──
@media (prefers-reduced-motion: no-preference) {
  .kpi-glow-accent {
    position: relative;

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 3px;
      background: linear-gradient(180deg, $mantis-neon, $mantis-green);
      border-radius: 3px 0 0 3px;
      animation: glowPulse 3s ease-in-out infinite;
    }
  }
}
```

**Step 2: Emergency stop button glow**

In `_custom.scss`, enhance existing `.emergency-stop-btn`:

```scss
.emergency-stop-btn {
  @media (prefers-reduced-motion: no-preference) {
    animation: emergencyPulse 2s ease-in-out infinite;
  }
}
```

**Step 3: Trading mode badge glow**

In `_custom.scss`, add:

```scss
// ── Mode badges ──
.mode-badge {
  &--demo { box-shadow: 0 0 8px rgba(255, 176, 32, 0.25); }
  &--live { box-shadow: 0 0 8px rgba(255, 61, 87, 0.3); animation: emergencyPulse 3s ease-in-out infinite; }
  &--paper { box-shadow: 0 0 8px rgba(0, 229, 255, 0.25); }
}
```

**Step 4: Section divider shimmer**

In `_custom.scss`, enhance `.section-divider__line`:

```scss
@media (prefers-reduced-motion: no-preference) {
  .section-divider__line {
    background: linear-gradient(90deg, transparent, rgba($mantis-green, 0.3), transparent);
    background-size: 200% 100%;
    animation: sectionShimmer 8s linear infinite;
  }
}
```

**Step 5: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 6: Commit**

```bash
git add frontend/src/scss/_custom.scss frontend/src/app/views/
git commit -m "ui: bolder — KPI glow, emergency pulse, mode badges, divider shimmer"
```

---

## Task 7: Layer 6 — Delight (memorable touches)

**Files:**
- Modify: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.html`
- Modify: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.scss`
- Modify: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.ts`

**Step 1: Bell shake on new notification**

In `notification-dropdown.component.ts`, add a `shaking` signal and logic to trigger it when `unreadCount` changes:

```typescript
readonly shaking = signal(false);

// In constructor or ngOnInit, watch unreadCount changes:
private prevCount = 0;

constructor() {
  effect(() => {
    const count = this.unreadCount();
    if (count > this.prevCount && this.prevCount >= 0) {
      this.shaking.set(true);
      setTimeout(() => this.shaking.set(false), 500);
    }
    this.prevCount = count;
  });
}
```

In `notification-dropdown.component.html`, add the `bell-shake` class conditionally to the bell button:

```html
<button ... [class.bell-shake]="shaking()">
```

In `notification-dropdown.component.scss`, add:

```scss
@keyframes bellShake {
  0%   { transform: rotate(0); }
  15%  { transform: rotate(12deg); }
  30%  { transform: rotate(-10deg); }
  45%  { transform: rotate(6deg); }
  60%  { transform: rotate(-3deg); }
  75%  { transform: rotate(1deg); }
  100% { transform: rotate(0); }
}

.bell-shake {
  animation: bellShake 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  transform-origin: top center;
}
```

**Step 2: Build verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors.

**Step 3: Commit**

```bash
git add frontend/src/app/layout/
git commit -m "ui: delight — notification bell shake on new alerts"
```

---

## Task 8: Final verification and build

**Step 1: Full build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors, 0 warnings.

**Step 2: Check git status**

Run: `git status`
Expected: clean working tree, all changes committed.

**Step 3: Push all commits**

```bash
git push origin master
```
