# MANTIS AI - Roadmap & Next Steps

> Current status: Phase 16 complete. 1065 tests, 0 errors. Production readiness ~95%.

---

## Phase 17: Performance & Monitoring (Immediate)

**Goal**: Observable, fast, production-grade backend.

### Database Performance
- [ ] Create composite indexes migration: `(trade_type, executed_at)`, `(epic, status)`, `(event_type, severity)`, `(created_at)` on key tables
- [ ] Configurable connection pool size (min/max) via environment variables
- [ ] Slow query logging (>500ms) with Polars-based analysis

### Observability
- [ ] Prometheus metrics endpoint (`GET /metrics`)
  - Request latency (p50, p95, p99)
  - Active WebSocket connections
  - Paper trading iteration time
  - ML prediction latency
  - Circuit breaker state
- [ ] Structured JSON logging (replace text logs)
- [ ] Background task health monitoring (detect stuck loops)

### Caching & Performance
- [ ] Redis-backed API response caching (10s TTL for dashboard, 60s for models)
- [ ] Pagination on all list endpoints (positions, signals, trades, events)
- [ ] Batch WebSocket price updates (debounce to 100ms intervals)

---

## Phase 18: Security Hardening (Short-term)

**Goal**: Production-safe authentication and security posture.

### Authentication
- [ ] HttpOnly cookie auth (replace localStorage JWT storage)
- [ ] Refresh token rotation (short-lived access + long-lived refresh)
- [ ] Account lockout after 5 failed login attempts (15min cooldown)
- [ ] Password strength validation with zxcvbn library

### HTTP Security
- [ ] Content Security Policy (CSP) headers in index.html
- [ ] CORS strict origin whitelist in production
- [ ] Helmet-style security headers (X-Frame-Options, X-Content-Type-Options, etc.)
- [ ] API versioning (`/api/v1/`) for breaking change management

### Input Validation
- [ ] Avatar upload streaming validation (file magic bytes, not just extension)
- [ ] Request body size limits per endpoint
- [ ] SQL injection audit on all raw queries (if any)

---

## Phase 19: UX Polish (Medium-term)

**Goal**: Smooth, accessible, responsive UI.

### Loading & Feedback
- [ ] Loading skeletons for all data-fetching components
- [ ] Optimistic UI updates for trade actions
- [ ] Toast notifications for background events (trade executed, circuit breaker)
- [ ] Empty state illustrations for pages with no data

### Accessibility
- [ ] ARIA labels on all interactive elements
- [ ] Keyboard navigation (Tab, Enter, Escape) for all modals/dropdowns
- [ ] Color contrast audit (WCAG 2.1 AA compliance)
- [ ] Screen reader testing on dashboard and trading pages

### Performance
- [ ] Service worker for offline dashboard viewing (PWA)
- [ ] HTTP retry interceptor with exponential backoff (network errors only)
- [ ] Centralized `DateFormatPipe` (replace scattered `toLocaleString` calls)
- [ ] Image lazy loading for avatar thumbnails

### Responsive Design
- [ ] Mobile-first dashboard layout (stack cards vertically on <768px)
- [ ] Touch-friendly chart interactions
- [ ] Collapsible sidebar on tablet

---

## Phase 20: Infrastructure & DevOps (Long-term)

**Goal**: Automated, scalable, production-deployed platform.

### Containerization
- [ ] Multi-stage Docker build (backend + frontend)
- [ ] Docker Compose production config (resource limits, restart policies)
- [ ] Environment-specific configs (dev, staging, production)

### CI/CD
- [ ] GitHub Actions pipeline:
  - Lint (ruff, ESLint)
  - Backend tests (pytest, coverage gate 80%)
  - Frontend build verification
  - Docker image build + push
  - Deploy to staging on PR merge
- [ ] Pre-commit hooks (ruff, mypy, prettier)
- [ ] Automated dependency updates (Dependabot)

### Database Operations
- [ ] Automated daily backups (pg_dump → S3/local)
- [ ] Backup restore testing (monthly)
- [ ] Database migration CI check (alembic upgrade dry-run)

---

## Phase 21: ML & Trading Enhancements (Future)

**Goal**: Better models, more strategies, live trading.

### Model Improvements
- [ ] Train XGBoost models for all 21 assets (currently 9 trained)
- [ ] Implement model drift detection (KS test on feature distributions)
- [ ] Automated monthly retraining pipeline
- [ ] SHAP feature importance dashboard
- [ ] A/B model testing framework (shadow mode)

### Advanced Models (Research)
- [ ] Revisit LSTM with larger dataset and optimized architecture
- [ ] Temporal Fusion Transformer (TFT) implementation
- [ ] Ensemble stacking (if multiple base models improve)
- [ ] Reinforcement learning for position sizing

### Data Enrichment
- [ ] FRED macro data pipeline (CPI, Fed Funds, DXY, VIX)
- [ ] FinBERT news sentiment scoring
- [ ] On-chain crypto metrics (hash rate, active addresses, exchange flows)
- [ ] Alternative data sources (social media sentiment, options flow)

### Live Trading
- [ ] Switch from Capital.com demo to live API
- [ ] Start with 0.5% risk per trade, 5% max exposure
- [ ] Real-time PnL monitoring + alerting (email/Slack)
- [ ] Gradual position size increase based on live performance
- [ ] Emergency kill switch (frontend + API)

---

## Phase 22: Scale & Monitor (Future)

**Goal**: Handle production load, monitor everything.

### Monitoring
- [ ] Grafana dashboards for Prometheus metrics
- [ ] Email/Slack alerting on:
  - Circuit breaker activation
  - Model accuracy degradation
  - System component failures
  - Daily P&L summary
- [ ] PagerDuty integration for critical alerts

### Load Testing
- [ ] Locust.io load tests (100 concurrent users)
- [ ] WebSocket connection stress test (1000 simultaneous)
- [ ] API response time benchmarks (target: p95 < 200ms)

### Scaling
- [ ] Redis cluster for high-availability caching
- [ ] Read replica for analytics queries
- [ ] Horizontal API scaling (stateless backend behind load balancer)
- [ ] Message queue for trade execution (prevent lost signals)

---

## Priority Matrix

| Priority | Phase | Effort | Impact |
|----------|-------|--------|--------|
| P0 (Now) | 17 — DB indexes + Prometheus | 2-3 days | High |
| P0 (Now) | 18 — HttpOnly cookies + CSP | 2-3 days | Critical (security) |
| P1 (Next) | 19 — Loading skeletons + accessibility | 3-5 days | Medium (UX) |
| P1 (Next) | 20 — Docker + CI/CD | 3-5 days | High (DevOps) |
| P2 (Later) | 21 — Train all 21 models + live prep | 1-2 weeks | High (business) |
| P3 (Future) | 22 — Grafana + load testing | 1 week | Medium (ops) |
