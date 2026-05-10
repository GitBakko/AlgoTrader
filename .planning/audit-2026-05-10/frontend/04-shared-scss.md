# Frontend Audit — Shared + SCSS (2026-05-10)

## Stats
- Total findings: 14 (CRITICAL: 3, HIGH: 6, MEDIUM: 5, LOW: 1)

---

## CRITICAL

### C1-SHARED: `_components.scss` L192-201: Untokenised hex for `.risk-badge--local` and `.risk-badge--none`

`#ffa726` (local-risk orange) and `#ef5350` (none-risk red) are hardcoded and appear nowhere in `_palette.scss`. The palette defines `$mantis-warning: #FFB020` and `$mantis-loss: #FF3D57` for exactly these semantic roles. The animation keyframes on L220-221 repeat the same raw hex.

**Confidence**: 95

**Fix**:
```scss
&--local {
  color: $mantis-warning;
  background: rgba($mantis-warning, 0.12);
  border: 1px solid rgba($mantis-warning, 0.35);
  animation: local-risk-pulse 3s ease-in-out infinite;
}

&--none {
  color: $mantis-loss;
  background: rgba($mantis-loss, 0.12);
  border: 1px solid rgba($mantis-loss, 0.35);
  animation: none-risk-pulse 2s ease-in-out infinite;
}

@keyframes none-risk-pulse {
  0%, 100% { opacity: 1; border-color: rgba($mantis-loss, 0.35); }
  50% { opacity: 0.8; border-color: rgba($mantis-loss, 0.7); }
}
```

---

### C2-SHARED: `epic-logo.component.ts` inline styles (`.logo-fallback`): Neon green as large background fill

`background-color: var(--mantis-neon, #39ff14)` fills the entire fallback logo placeholder. CLAUDE.md is explicit: "Neon green `#39FF14` on large areas — accent only." The logo box (default 32×32, up to 96×96) renders a solid neon-green background for any asset without a logo — a large area fill. Should use a surface elevation token instead.

**File**: `frontend/src/app/shared/components/epic-logo/epic-logo.component.ts:63-72`
**Confidence**: 90

**Fix**:
```scss
.logo-fallback {
  background-color: var(--mantis-surface-3, #1c2128);   // elevation, not neon
  border: 1px solid var(--mantis-border-accent);
  border-radius: var(--mantis-radius-sm, 4px);

  .fallback-text {
    color: var(--mantis-neon, #39FF14);   // neon only on text (small area)
    font-weight: 700;
    font-size: 0.75em;
    text-transform: uppercase;
  }
}
```

---

### C3-SHARED: `news-widget.component.scss` L67: Fictional CSS var `--cui-mantis-green` never resolves

```scss
color: var(--cui-mantis-green, #00d97e);
```

`--cui-mantis-green` is not defined anywhere in `:root` or any theme override. Browser always falls through to `#00d97e` literal fallback. Correct token is `var(--mantis-green)` (defined in `_custom.scss` `:root`).

**File**: `frontend/src/app/shared/components/news-widget/news-widget.component.scss:67`
**Confidence**: 100

**Fix**: `color: var(--mantis-green);`

---

## HIGH

### H1-SHARED: `user-dropdown.component.ts`: Missing `ChangeDetectionStrategy.OnPush`

Component uses signals (`computed`) so OnPush is both safe and mandatory.

**File**: `frontend/src/app/layout/default-layout/default-header/user-dropdown/user-dropdown.component.ts:20`
**Fix**: Add `changeDetection: ChangeDetectionStrategy.OnPush` and import.

### H2-SHARED: `default-footer.component.ts`: Missing `ChangeDetectionStrategy.OnPush`

Component is purely presentational — OnPush is trivially safe.

**File**: `frontend/src/app/layout/default-layout/default-footer/default-footer.component.ts`

### H3-SHARED: `default-layout.component.ts`: Missing `ChangeDetectionStrategy.OnPush`

Shell layout has no `changeDetection`. Renders router-outlet and static nav.

**File**: `frontend/src/app/layout/default-layout/default-layout.component.ts:25`

### H4-SHARED: `user-dropdown.component.scss` L144: Wrong dark-mode media query hook

```scss
@media (prefers-color-scheme: dark) {
  .user-dropdown { ... }
}
```

App uses CoreUI's attribute-based theming: `[data-coreui-theme="dark"]`. OS-preference hook does not fire when user manually switches theme in the app. Dropdown hover/shadow styles skipped when user is in dark mode via UI toggle (most common path).

**Fix**: Replace with `[data-coreui-theme="dark"] { ... }`.

### H5-SHARED: `news-widget.component.scss` L5: Fixed pixel `max-height: 600px` on content container

CLAUDE.md: "Fixed pixel heights on content containers (breaks responsive)." `.news-grid` clipped at 600px regardless of viewport.

**Fix**: Use `max-height: 60vh` or remove cap.

### H6-SHARED: `_auth.scss` L93: `#00ff88` hardcoded, not a palette token

`.auth-blob.blob-3` uses hex not in palette — close but not equal to `$mantis-neon` or `$mantis-green`.

**Fix**: `background: radial-gradient(circle, $mantis-green, transparent);`

---

## MEDIUM

### M1-SHARED: `signal-audit-drawer.component.scss` L629/635: `color: #000` not a token
Use `var(--mantis-bg, #0d1117)`.

### M2-SHARED: `_auth.scss` L235/239: `#ff6b7a` hardcoded alert/feedback colour
Map to `$mantis-loss: #FF3D57`.

### M3-SHARED: `_auth.scss` L305/306: `#dc3545`/`#ffc107` for password-strength meter
Map to `$mantis-loss` and `$mantis-warning`.

### M4-SHARED: `bottom-nav.component.ts`: Missing `ChangeDetectionStrategy.OnPush`
Purely template-driven. Safe to add OnPush.

### M5-SHARED: `_auth.scss` L228-229/415-416: Unscoped element selectors `h1 {}` and `p {}`
Inside `.auth-form-section` / `.auth-card`. Add explicit classes.

---

## LOW

### L1-SHARED: `toast-container.component.scss` L13: `z-index: 1090` exceeds CLAUDE.md limit

Justified by inline comment (toasts must layer above modals at 1050). Add named exception in CLAUDE.md.

---

## Notes
- No `lighten()`/`darken()` calls found. `color.adjust()` used correctly.
- No `console.log` in shared TS files.
- KPI pattern (top accent bar) correctly implemented.
- Audit drawer correctly uses `deal_id` matching (consistent with `dea2a29` fix).
- **Most impactful fix**: H4 (wrong dark-mode media query) — theme switching via UI toggle is primary use case; silently breaks dark-mode dropdown for users without OS dark mode.
