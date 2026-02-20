# Notification Center — Design Document

**Date**: 2026-02-20
**Status**: Approved
**Approach**: A (AlertManager as single source)

## Overview

Add an in-app notification center so the user can browse alerts they missed while offline. The AlertManager already creates Alert objects for every event (trades, risk, system). We add an **InAppChannel** that persists to DB and broadcasts via WebSocket — always active, independent of `ALERTS_ENABLED` (which controls external channels: Telegram/Email/Slack).

## Backend

### DB Model — `notifications` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL PK | |
| `alert_type` | VARCHAR(50) | TRADE_OPENED, CIRCUIT_BREAKER, etc. |
| `severity` | VARCHAR(20) | CRITICAL, WARNING, INFO |
| `title` | VARCHAR(300) | |
| `message` | TEXT | |
| `epic` | VARCHAR(50) | nullable |
| `details` | JSONB | flexible payload |
| `is_read` | BOOLEAN | default false |
| `created_at` | TIMESTAMP | server_default NOW() |

Index: `(is_read, created_at DESC)` for fast "unread, recent" queries.

### InAppChannel

New channel class in `alert_manager.py` (or separate file) implementing `AlertChannel`:
- `send(alert)`: INSERT into `notifications` table + `ws_manager.broadcast("notifications", payload)`
- Always added to `AlertManager.channels`, regardless of `ALERTS_ENABLED`
- Uses `db_session_factory` for DB access (same pattern as ExecutionEngine)

### API Endpoints — `/api/notifications`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/notifications` | Paginated list (page, page_size, type, severity, epic, is_read) |
| `GET` | `/api/notifications/unread-count` | Unread count only |
| `PUT` | `/api/notifications/{id}/read` | Mark single as read |
| `PUT` | `/api/notifications/read-all` | Mark all as read |
| `DELETE` | `/api/notifications/{id}` | Delete single |

### WebSocket — `/ws/notifications`

New WS endpoint. Frontend connects on app init. Receives real-time alert payloads:

```json
{
  "id": 42,
  "alert_type": "TRADE_CLOSED",
  "severity": "INFO",
  "title": "Trade Chiuso: XAUUSD",
  "message": "BUY chiuso con profitto +$45.20",
  "epic": "XAUUSD",
  "emoji": "💰",
  "details": {"deal_id": "DEAL-123", "pnl": 45.20},
  "is_read": false,
  "created_at": "2026-02-20T16:30:00Z"
}
```

## Frontend

### NotificationCenterService (`core/services/notification-center.service.ts`)

Signals:
- `notifications: Signal<Notification[]>` — recent list for dropdown
- `unreadCount: Signal<number>` — badge number

Methods:
- `loadRecent()` — GET /api/notifications?page_size=10&is_read=false
- `loadUnreadCount()` — GET /api/notifications/unread-count
- `markAsRead(id)` — PUT /api/notifications/{id}/read
- `markAllRead()` — PUT /api/notifications/read-all
- `delete(id)` — DELETE /api/notifications/{id}
- `loadPage(filters)` — GET /api/notifications with full filters

WebSocket:
- Connects to `/ws/notifications` on init
- On message: prepend to `notifications`, increment `unreadCount`
- Reconnect with exponential backoff (same pattern as existing WS)

### Header Bell Icon

Between WS status pill and theme toggle:
- `cilBell` icon with red badge showing `unreadCount`
- CoreUI dropdown on click
- Each row: emoji (from ALERT_EMOJI) + title + relative time + unread dot
- Max ~10 items in dropdown
- Footer: "Segna tutte come lette" button + "Vedi tutte" link to `/notifications`

### Notifications Page (`/notifications`)

- Route: `/notifications` (lazy loaded)
- Filter bar: type select, severity select, asset select, date range, "solo non lette" toggle
- Paginated table: emoji, title, message (truncated), asset, severity badge, relative time, actions
- Top KPI: total unread, by severity breakdown

### Notification TypeScript Model

```typescript
export interface AppNotification {
  id: number;
  alert_type: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  title: string;
  message: string;
  epic?: string;
  emoji: string;
  details: Record<string, any>;
  is_read: boolean;
  created_at: string;
}
```

## Data Flow

```
AlertManager.send_alert(alert)
  ├── InAppChannel.send(alert)       ← ALWAYS active
  │   ├── DB INSERT notifications
  │   └── ws_manager.broadcast("notifications", ...)
  ├── TelegramChannel.send()         ← if ALERTS_ENABLED
  ├── EmailChannel.send()            ← if ALERTS_ENABLED
  └── SlackChannel.send()            ← if ALERTS_ENABLED

Frontend:
  WS /ws/notifications → NotificationCenterService
    → unreadCount signal → Bell badge
    → notifications signal → Dropdown list
  REST /api/notifications → Notifications page (full history)
```

## Files to Create/Modify

### New Files
- `backend/alembic/versions/xxxx_add_notifications.py` — migration
- `backend/src/database/repositories/notification_repository.py` — CRUD
- `backend/src/monitoring/alerting/in_app_channel.py` — InAppChannel
- `backend/src/api/routers/notifications.py` — REST endpoints
- `backend/tests/api/test_notifications.py` — API tests
- `backend/tests/monitoring/test_in_app_channel.py` — channel tests
- `frontend/src/app/core/services/notification-center.service.ts` — service
- `frontend/src/app/core/models/notification.model.ts` — TypeScript model
- `frontend/src/app/layout/default-layout/default-header/notification-dropdown/` — dropdown component
- `frontend/src/app/views/notifications/` — full page

### Modified Files
- `backend/src/database/models.py` — add Notification model
- `backend/src/database/repositories/__init__.py` — export new repo
- `backend/src/monitoring/alerting/alert_manager.py` — add InAppChannel
- `backend/src/api/main.py` — register notifications router + WS endpoint
- `backend/src/api/websocket.py` — add /ws/notifications endpoint
- `frontend/src/app/layout/default-layout/default-header/default-header.component.ts` — add bell
- `frontend/src/app/layout/default-layout/default-header/default-header.component.html` — bell UI
- `frontend/src/app/layout/default-layout/_nav.ts` — add Notifiche nav item
- `frontend/src/app/app.routes.ts` — add /notifications route
- `frontend/src/app/core/models/index.ts` — export notification model
- `frontend/src/app/shared/components/icon-subset.ts` — ensure cilBell exists
