# MANTIS AI — Full Visual Polish Design

**Date**: 2026-03-02
**Approach**: Layer-by-layer (Approach A)
**Scope**: All pages, global styles, animations

## Current State

Overall visual quality: 7.8/10. Excellent design system foundation (palette, typography, surfaces, elevation). Dashboard and Positions are polished (8/10). Signals page is the weakest (6.5/10). Missing entrance animations across all pages. Micro-interactions and hover effects inconsistent.

## Layer 1: Normalize

Align all pages to the MANTIS design system for consistency.

### 1.1 Signals Page — Add KPI Summary Row
- Add 4 KPI cards above the table: Total Signals, Executed %, Avg Confidence, Top Strategy
- Use same KPI card pattern as Dashboard (border-top-3 border-top-primary, mantis-kpi class)
- Compute from existing signal data in component

### 1.2 Confidence Bar Thickness
- Increase from 4px to 6px on all pages (Signals, Paper Trading)
- Apply via `.conf-bar-wrapper` class in `_custom.scss`

### 1.3 Card Pattern Consistency
- Verify all content cards use `border-top border-top-3 border-top-primary`
- Audit: Signals, Markets, Settings — ensure no plain cards without accent

### 1.4 Filter Input Consistency
- Same green-focus-glow (`box-shadow: 0 0 0 2px rgba(0, 217, 126, 0.15)`) on all form inputs
- Currently present on Positions page — extend to Signals, Settings

## Layer 2: Polish

Fix spacing, alignment, detail issues.

### 2.1 Table Row Hover
- Uniform hover background tint on ALL data tables
- `tbody tr:hover { background: rgba(255,255,255,0.03); }` in `_custom.scss`
- Currently inconsistent between pages

### 2.2 Tab Bar Separator
- Add subtle bottom border between Positions tab bar and content
- `border-bottom: 1px solid var(--mantis-border-subtle)`

### 2.3 Selected Asset Card (Markets)
- Amplify selection: add background tint (`rgba($mantis-green, 0.05)`) in addition to left border
- Make selected state more obvious at a glance

### 2.4 Notification Bell Pulse
- Add pulse dot indicator on bell icon when unread count > 0
- Use existing `pulse-dot` class from design system

## Layer 3: Animate

New keyframes in `_motion.scss`, utility classes for reuse.

### 3.1 `@keyframes fadeSlideUp`
```css
@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-in {
  animation: fadeSlideUp 0.4s ease-out both;
}
```
Apply to: cards, KPI rows, table containers on page load.

### 3.2 `@keyframes fadeIn`
```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
.fade-in {
  animation: fadeIn 0.25s ease-out both;
}
```
Apply to: badges, chips, status indicators.

### 3.3 Staggered Entrance
```css
.stagger-1 { animation-delay: 50ms; }
.stagger-2 { animation-delay: 100ms; }
.stagger-3 { animation-delay: 150ms; }
.stagger-4 { animation-delay: 200ms; }
```
Apply to: KPI card grids, dashboard sections.

### 3.4 Data Refresh Flash
```css
@keyframes valueFlash {
  0% { background-color: transparent; }
  30% { background-color: rgba(0, 217, 126, 0.12); }
  100% { background-color: transparent; }
}
.value-flash {
  animation: valueFlash 0.6s ease-out;
}
```
Apply programmatically when price/P&L values change.

### 3.5 Skeleton Shimmer (for chart loading)
```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton-shimmer {
  background: linear-gradient(90deg, var(--mantis-surface-2) 25%, var(--mantis-surface-3) 50%, var(--mantis-surface-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
```

## Layer 4: Colorize

Strategic color where UI is too monochromatic.

### 4.1 Regime Badge Tints
- `trending_up` → green background tint (`rgba($mantis-profit, 0.10)`)
- `trending_down` → red background tint (`rgba($mantis-loss, 0.10)`)
- `ranging` → amber background tint (`rgba($mantis-warning, 0.10)`)

### 4.2 Confidence Gradient
- Replace binary success/warning with 3-tier gradient:
  - < 30%: danger red
  - 30-50%: warning amber
  - > 50%: success green

### 4.3 P&L Row Tint
- Rows with positive P&L: `rgba($mantis-profit, 0.04)` background
- Rows with negative P&L: `rgba($mantis-loss, 0.04)` background
- Subtle enough to not distract, visible enough to scan quickly

### 4.4 Active Nav Glow
- Sidebar active item: amplify glow from current border-left to include subtle box-shadow

## Layer 5: Bolder

Amplify designs that are too safe.

### 5.1 Dashboard KPI Glow
- Left accent bar on KPI cards: add slow pulsing glow animation (3s, subtle)
- Only on the primary KPI (Account Balance or Daily P&L)

### 5.2 Emergency Stop Glow
- Red pulsing glow on Emergency Stop button (already exists as class, amplify)
- `box-shadow: 0 0 12px rgba(255, 61, 87, 0.4)` pulsing

### 5.3 Trading Mode Badge
- DEMO: amber glow + pulse
- LIVE: red glow + stronger pulse
- PAPER: cyan glow + gentle pulse
- Each visually distinct at a glance

### 5.4 Section Divider Shimmer
- Gradient line gets a subtle traveling shimmer effect (15s infinite, very subtle)

## Layer 6: Delight

Memorable touches.

### 6.1 Notification Bell Shake
- When unread count increments: `@keyframes bellShake` (3deg oscillation, 0.4s)
- Triggered once per new notification, not continuous

### 6.2 P&L Counter Tween
- When P&L values update, animate from old → new value over 300ms
- Use `CountUp` pattern (requestAnimationFrame) in component

### 6.3 Profit Flash
- When a position closes in profit: brief green flash on the Total P&L KPI card
- Use `valueFlash` animation from Layer 3

### 6.4 Custom Tooltips
- Replace browser-default tooltips on CB badges with styled custom tooltips
- Use CoreUI's `cTooltip` directive (already in use) but ensure custom styling applied

## Files Modified

| File | Layers | Changes |
|------|--------|---------|
| `_motion.scss` | 3, 5, 6 | New keyframes: fadeSlideUp, fadeIn, valueFlash, shimmer, bellShake, sectionShimmer |
| `_custom.scss` | 1, 2, 4, 5 | Table hover, confidence bar, P&L tints, nav glow, badge colors, KPI glow |
| `_palette.scss` | 4 | Regime tint tokens if needed |
| `signals.component.html` | 1 | KPI summary row |
| `signals.component.ts` | 1 | Computed signals for KPI metrics |
| `paper-trading.component.ts` | 2, 3 | Hover effects, animate-in classes |
| `positions.component.html` | 2, 3 | Tab separator, animate-in |
| `markets.component.html/scss` | 2, 3 | Selected card tint, animate-in |
| `dashboard.component.html/scss` | 3, 5 | Staggered entrance, KPI glow |
| `default-header` | 6 | Bell shake animation |
| Various templates | 3 | animate-in, stagger-N classes |

## What We Do NOT Touch
- TradingView chart internals (tv-chart component logic)
- Routing structure
- Service logic / API calls
- Auth flow (guards, interceptors, JWT)
- Backend code
- Test files

## Respects `prefers-reduced-motion`
All new animations wrapped in `@media (prefers-reduced-motion: no-preference)` — users who prefer reduced motion see instant rendering without animation.
