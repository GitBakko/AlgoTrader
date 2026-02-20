# Notification Center Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an in-app notification center (DB persistence + WS real-time push + REST API + header bell dropdown + dedicated page) so the user can see alerts they missed while offline.

**Architecture:** The AlertManager already creates Alert objects for every event. We add an InAppChannel (always active, independent of ALERTS_ENABLED) that persists alerts to PostgreSQL and broadcasts via WebSocket. The frontend connects to a new `/ws/notifications` channel and displays notifications in a header dropdown + full page.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), Angular 21/CoreUI (frontend), PostgreSQL (persistence), WebSocket (real-time push)

**Design Doc:** `docs/plans/2026-02-20-notification-center-design.md`

---

## Task 1: Backend — Notification DB Model

**Files:**
- Modify: `backend/src/database/models.py` (append after MarketSpec class, ~line 487)

**Step 1: Add Notification model**

Append after `MarketSpec` class in `models.py`:

```python
class Notification(SQLModel, table=True):
    """
    In-app notifications persisted from AlertManager.
    Each alert generates one notification row for the UI notification center.
    """

    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    alert_type: str = Field(max_length=50, nullable=False, index=True)
    severity: str = Field(max_length=20, nullable=False, index=True)
    title: str = Field(max_length=300, nullable=False)
    message: str = Field(nullable=False)
    epic: Optional[str] = Field(default=None, max_length=50, index=True)
    details: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    is_read: bool = Field(default=False, nullable=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        sa_column_kwargs={"server_default": text("NOW()")},
    )
```

**Step 2: Verify import**

The file already imports `JSONB`, `BigInteger`, `Column`, `text` from sqlalchemy — no new imports needed.

---

## Task 2: Backend — Alembic Migration

**Files:**
- Create: `backend/alembic/versions/2026_02_20_1700-a1b2c3d4e5f6_add_notifications_table.py`

**Step 1: Create migration file**

```python
"""Add notifications table for in-app notification center.

Revision ID: a1b2c3d4e5f6
Revises: f5a8b3c2d1e0
Create Date: 2026-02-20 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f6"
down_revision = "f5a8b3c2d1e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("epic", sa.String(50), nullable=True, index=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    # Composite index for "unread + recent" queries (dropdown + badge count)
    op.create_index(
        "ix_notifications_unread_recent",
        "notifications",
        ["is_read", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_unread_recent", table_name="notifications")
    op.drop_table("notifications")
```

**Step 2: Apply migration**

```bash
cd backend && .venv/Scripts/python.exe -m alembic upgrade head
```

---

## Task 3: Backend — NotificationRepository

**Files:**
- Create: `backend/src/database/repositories/notification_repository.py`
- Modify: `backend/src/database/repositories/__init__.py` (add export)

**Step 1: Create repository**

```python
"""
Repository for in-app notifications (CRUD + pagination).
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Notification


class NotificationRepository:
    """Repository for notification persistence and retrieval."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        epic: str | None = None,
        details: dict | None = None,
    ) -> Notification:
        """Insert a new notification."""
        notif = Notification(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            epic=epic,
            details=details,
        )
        self.session.add(notif)
        await self.session.flush()
        return notif

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        alert_type: str | None = None,
        severity: str | None = None,
        epic: str | None = None,
        is_read: bool | None = None,
    ) -> tuple[list[Notification], int]:
        """Get paginated notifications with optional filters. Returns (items, total)."""
        query = select(Notification)
        count_query = select(func.count()).select_from(Notification)

        if alert_type:
            query = query.where(Notification.alert_type == alert_type)
            count_query = count_query.where(Notification.alert_type == alert_type)
        if severity:
            query = query.where(Notification.severity == severity)
            count_query = count_query.where(Notification.severity == severity)
        if epic:
            query = query.where(Notification.epic == epic)
            count_query = count_query.where(Notification.epic == epic)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
            count_query = count_query.where(Notification.is_read == is_read)

        total = (await self.session.execute(count_query)).scalar() or 0

        query = query.order_by(Notification.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        result = await self.session.execute(
            select(func.count()).select_from(Notification).where(Notification.is_read == False)
        )
        return result.scalar() or 0

    async def mark_as_read(self, notification_id: int) -> bool:
        """Mark a single notification as read. Returns True if found."""
        result = await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(is_read=True)
        )
        return result.rowcount > 0

    async def mark_all_read(self) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        result = await self.session.execute(
            update(Notification)
            .where(Notification.is_read == False)
            .values(is_read=True)
        )
        return result.rowcount

    async def delete_one(self, notification_id: int) -> bool:
        """Delete a single notification. Returns True if found."""
        result = await self.session.execute(
            delete(Notification).where(Notification.id == notification_id)
        )
        return result.rowcount > 0
```

**Step 2: Export from `__init__.py`**

Add to `backend/src/database/repositories/__init__.py`:
- Import: `from src.database.repositories.notification_repository import NotificationRepository`
- Add `"NotificationRepository"` to `__all__`

---

## Task 4: Backend — InAppChannel

**Files:**
- Create: `backend/src/monitoring/alerting/in_app_channel.py`

**Step 1: Create the channel**

```python
"""
In-app notification channel.
Persists alerts to PostgreSQL and broadcasts via WebSocket.
Always active, independent of ALERTS_ENABLED setting.
"""

from loguru import logger

from src.monitoring.alerting.channels import AlertChannel
from src.monitoring.alerting.schemas import ALERT_EMOJI, SEVERITY_EMOJI, Alert, AlertType


class InAppChannel(AlertChannel):
    """
    Persists alerts to the notifications DB table and broadcasts via WS.
    Requires db_session_factory to be injected after app startup.
    """

    def __init__(self):
        self._db_session_factory = None

    def set_db_session_factory(self, factory) -> None:
        """Inject DB session factory (called during app lifespan startup)."""
        self._db_session_factory = factory

    async def send(self, alert: Alert) -> bool:
        """Persist alert to DB and broadcast via WebSocket."""
        notification_id = None

        # 1. Persist to DB
        if self._db_session_factory:
            try:
                from src.database.repositories.notification_repository import (
                    NotificationRepository,
                )

                async with self._db_session_factory() as session:
                    repo = NotificationRepository(session)
                    notif = await repo.create(
                        alert_type=alert.alert_type.value,
                        severity=alert.severity.value,
                        title=alert.title,
                        message=alert.message,
                        epic=alert.epic,
                        details=alert.details,
                    )
                    notification_id = notif.id
                    await session.commit()
            except Exception as e:
                logger.warning(f"InAppChannel DB persist failed: {e}")

        # 2. Broadcast via WebSocket
        try:
            from src.api.websocket import ws_manager

            emoji = self._get_emoji(alert)
            payload = {
                "id": notification_id,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "epic": alert.epic,
                "emoji": emoji,
                "details": alert.details,
                "is_read": False,
                "created_at": alert.timestamp.isoformat(),
            }
            await ws_manager.broadcast("notifications", payload)
        except Exception as e:
            logger.warning(f"InAppChannel WS broadcast failed: {e}")

        return True

    @staticmethod
    def _get_emoji(alert: Alert) -> str:
        """Get emoji for alert type (reuse logic from Alert._get_emoji)."""
        emoji = ALERT_EMOJI.get(alert.alert_type, SEVERITY_EMOJI.get(alert.severity, "🔵"))
        if alert.alert_type == AlertType.TRADE_CLOSED:
            pnl = alert.details.get("pnl")
            if pnl is not None:
                try:
                    if float(pnl) < 0:
                        emoji = "🔻"
                except (ValueError, TypeError):
                    pass
        return emoji
```

---

## Task 5: Backend — Wire InAppChannel into AlertManager

**Files:**
- Modify: `backend/src/monitoring/alerting/alert_manager.py`

**Step 1: Add InAppChannel import and initialization**

At the top imports, add:
```python
from src.monitoring.alerting.in_app_channel import InAppChannel
```

**Step 2: Add InAppChannel in `__init__` (before `_initialize_channels`)**

After `self.channels: list[AlertChannel] = []`, add:
```python
# In-app channel is always active (DB + WS broadcast)
self.in_app_channel = InAppChannel()
self.channels.append(self.in_app_channel)
```

**Step 3: Update the "no channels" warning**

Change the check `if not self.channels:` at end of `_initialize_channels` to:
```python
if len(self.channels) <= 1:  # Only InAppChannel
    logger.warning("No external alert channels configured. Alerts will only be in-app.")
```

**Step 4: Update `send_alert` to handle empty channels**

Remove the early return `if not self.channels: return {}` — InAppChannel is always present.

---

## Task 6: Backend — WebSocket Notifications Endpoint

**Files:**
- Modify: `backend/src/api/websocket.py` (add `notifications_endpoint` function)

**Step 1: Add notifications endpoint**

Append after `trades_endpoint`:

```python
async def notifications_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time in-app notifications."""
    await ws_manager.connect(websocket, "notifications")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, "notifications")
```

---

## Task 7: Backend — Notifications REST Router

**Files:**
- Create: `backend/src/api/routers/notifications.py`

**Step 1: Create router**

```python
"""
Notifications API router.
In-app notification center: list, read, mark-as-read, delete.
"""

from fastapi import APIRouter, Depends, Query
from loguru import logger

from src.api.dependencies import get_db_session
from src.api.schemas import error_response, success_response
from src.database.repositories.notification_repository import NotificationRepository
from src.monitoring.alerting.schemas import ALERT_EMOJI, SEVERITY_EMOJI

router = APIRouter()


def _get_repo(session):
    """Create NotificationRepository from session."""
    if session is None:
        return None
    return NotificationRepository(session)


@router.get("/")
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alert_type: str | None = Query(None),
    severity: str | None = Query(None),
    epic: str | None = Query(None),
    is_read: bool | None = Query(None),
    session=Depends(get_db_session),
):
    """List notifications with pagination and filters."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    items, total = await repo.get_list(
        page=page,
        page_size=page_size,
        alert_type=alert_type,
        severity=severity,
        epic=epic,
        is_read=is_read,
    )

    notifications = []
    for n in items:
        emoji = ALERT_EMOJI.get(n.alert_type, SEVERITY_EMOJI.get(n.severity, "🔵"))
        notifications.append({
            "id": n.id,
            "alert_type": n.alert_type,
            "severity": n.severity,
            "title": n.title,
            "message": n.message,
            "epic": n.epic,
            "emoji": emoji,
            "details": n.details,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })

    return success_response({
        "notifications": notifications,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/unread-count")
async def unread_count(session=Depends(get_db_session)):
    """Get count of unread notifications."""
    repo = _get_repo(session)
    if repo is None:
        return success_response({"count": 0})

    count = await repo.get_unread_count()
    return success_response({"count": count})


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: int, session=Depends(get_db_session)):
    """Mark a single notification as read."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    found = await repo.mark_as_read(notification_id)
    if not found:
        return error_response("Notification not found", 404)
    return success_response({"message": "Marked as read"})


@router.put("/read-all")
async def mark_all_read(session=Depends(get_db_session)):
    """Mark all notifications as read."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    count = await repo.mark_all_read()
    return success_response({"message": f"Marked {count} as read", "count": count})


@router.delete("/{notification_id}")
async def delete_notification(notification_id: int, session=Depends(get_db_session)):
    """Delete a single notification."""
    repo = _get_repo(session)
    if repo is None:
        return error_response("Database not available", 503)

    found = await repo.delete_one(notification_id)
    if not found:
        return error_response("Notification not found", 404)
    return success_response({"message": "Deleted"})
```

---

## Task 8: Backend — Register Router + WS + Inject DB Factory

**Files:**
- Modify: `backend/src/api/main.py`

**Step 1: Import new router and WS endpoint**

At line 22-36 (router imports), add `notifications`:
```python
from src.api.routers import (
    auth, backtest, dashboard, export, markets, models,
    monitoring, news, notifications, positions, signals, strategy, system, trading,
)
```

At line 37 (websocket imports), add `notifications_endpoint`:
```python
from src.api.websocket import notifications_endpoint, prices_endpoint, trades_endpoint
```

**Step 2: Register router** (after line 647, with the other routers)

```python
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
```

**Step 3: Register WS endpoint** (after line 652)

```python
app.websocket("/ws/notifications")(notifications_endpoint)
```

**Step 4: Inject DB session factory into InAppChannel** (in `lifespan`, after DB is initialized)

Find the section where `app.state.db_session_factory` is set and add after it:

```python
# Inject DB factory into InAppChannel for notification persistence
from src.monitoring.alerting.alert_manager import get_alert_manager
alert_mgr = get_alert_manager()
if hasattr(alert_mgr, 'in_app_channel') and app.state.db_session_factory:
    alert_mgr.in_app_channel.set_db_session_factory(app.state.db_session_factory)
    logger.info("InAppChannel DB session factory injected")
```

---

## Task 9: Backend — Tests

**Files:**
- Create: `backend/tests/api/test_notifications.py`

**Step 1: Write API tests**

```python
"""Tests for notifications API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_notification():
    """Create a mock notification object."""
    notif = MagicMock()
    notif.id = 1
    notif.alert_type = "TRADE_OPENED"
    notif.severity = "INFO"
    notif.title = "Trade Opened: XAUUSD BUY"
    notif.message = "BUY XAUUSD size=0.1 @ 5000.00"
    notif.epic = "XAUUSD"
    notif.details = {"deal_id": "DEAL-1", "direction": "BUY"}
    notif.is_read = False
    notif.created_at = MagicMock(isoformat=MagicMock(return_value="2026-02-20T16:00:00"))
    return notif


class TestNotificationsAPI:
    """Test notification REST endpoints."""

    @pytest.mark.asyncio
    async def test_list_notifications(self, client, mock_notification):
        with patch(
            "src.api.routers.notifications.get_db_session"
        ) as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            with patch(
                "src.api.routers.notifications.NotificationRepository"
            ) as MockRepo:
                repo_instance = AsyncMock()
                repo_instance.get_list.return_value = ([mock_notification], 1)
                MockRepo.return_value = repo_instance

                response = client.get("/api/notifications/")
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert len(data["data"]["notifications"]) == 1
                assert data["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_unread_count(self, client):
        with patch(
            "src.api.routers.notifications.get_db_session"
        ) as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            with patch(
                "src.api.routers.notifications.NotificationRepository"
            ) as MockRepo:
                repo_instance = AsyncMock()
                repo_instance.get_unread_count.return_value = 5
                MockRepo.return_value = repo_instance

                response = client.get("/api/notifications/unread-count")
                assert response.status_code == 200
                data = response.json()
                assert data["data"]["count"] == 5

    @pytest.mark.asyncio
    async def test_mark_as_read(self, client):
        with patch(
            "src.api.routers.notifications.get_db_session"
        ) as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            with patch(
                "src.api.routers.notifications.NotificationRepository"
            ) as MockRepo:
                repo_instance = AsyncMock()
                repo_instance.mark_as_read.return_value = True
                MockRepo.return_value = repo_instance

                response = client.put("/api/notifications/1/read")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_mark_all_read(self, client):
        with patch(
            "src.api.routers.notifications.get_db_session"
        ) as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            with patch(
                "src.api.routers.notifications.NotificationRepository"
            ) as MockRepo:
                repo_instance = AsyncMock()
                repo_instance.mark_all_read.return_value = 3
                MockRepo.return_value = repo_instance

                response = client.put("/api/notifications/read-all")
                assert response.status_code == 200
                assert response.json()["data"]["count"] == 3

    @pytest.mark.asyncio
    async def test_delete_notification(self, client):
        with patch(
            "src.api.routers.notifications.get_db_session"
        ) as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value = mock_session

            with patch(
                "src.api.routers.notifications.NotificationRepository"
            ) as MockRepo:
                repo_instance = AsyncMock()
                repo_instance.delete_one.return_value = True
                MockRepo.return_value = repo_instance

                response = client.delete("/api/notifications/1")
                assert response.status_code == 200
```

**Step 2: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q --tb=short
```

---

## Task 10: Frontend — Notification Model + Service

**Files:**
- Create: `frontend/src/app/core/models/notification.model.ts`
- Modify: `frontend/src/app/core/models/index.ts` (add export)
- Create: `frontend/src/app/core/services/notification-center.service.ts`

**Step 1: Create notification model**

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

export interface NotificationListResponse {
  notifications: AppNotification[];
  total: number;
  page: number;
  page_size: number;
}
```

**Step 2: Export from `index.ts`**

Add at end of `frontend/src/app/core/models/index.ts`:
```typescript
export * from './notification.model';
```

**Step 3: Create NotificationCenterService**

```typescript
import { Injectable, inject, signal, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { ApiResponse, AppNotification, NotificationListResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class NotificationCenterService implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/notifications`;
  private readonly wsUrl = `${environment.wsUrl}/ws/notifications`;

  readonly notifications = signal<AppNotification[]>([]);
  readonly unreadCount = signal(0);

  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private readonly MAX_RECONNECT_DELAY = 60000;
  private readonly BASE_DELAY = 2000;

  /** Initialize: load from REST + connect WS */
  init(): void {
    this.loadUnreadCount();
    this.loadRecent();
    this.connectWs();
  }

  /** Load recent unread notifications for dropdown */
  loadRecent(): void {
    this.http.get<ApiResponse<NotificationListResponse>>(
      `${this.apiUrl}/?page=1&page_size=20`
    ).subscribe({
      next: res => {
        if (res.success) {
          this.notifications.set(res.data.notifications);
        }
      }
    });
  }

  /** Load unread count for badge */
  loadUnreadCount(): void {
    this.http.get<ApiResponse<{ count: number }>>(
      `${this.apiUrl}/unread-count`
    ).subscribe({
      next: res => {
        if (res.success) {
          this.unreadCount.set(res.data.count);
        }
      }
    });
  }

  /** Load paginated notifications (for full page) */
  loadPage(params: {
    page?: number;
    page_size?: number;
    alert_type?: string;
    severity?: string;
    epic?: string;
    is_read?: boolean;
  } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.page_size) query.set('page_size', String(params.page_size));
    if (params.alert_type) query.set('alert_type', params.alert_type);
    if (params.severity) query.set('severity', params.severity);
    if (params.epic) query.set('epic', params.epic);
    if (params.is_read !== undefined) query.set('is_read', String(params.is_read));

    return this.http.get<ApiResponse<NotificationListResponse>>(
      `${this.apiUrl}/?${query.toString()}`
    );
  }

  /** Mark single notification as read */
  markAsRead(id: number): void {
    this.http.put<ApiResponse<any>>(`${this.apiUrl}/${id}/read`, {}).subscribe({
      next: () => {
        this.notifications.update(list =>
          list.map(n => n.id === id ? { ...n, is_read: true } : n)
        );
        this.unreadCount.update(c => Math.max(0, c - 1));
      }
    });
  }

  /** Mark all as read */
  markAllRead(): void {
    this.http.put<ApiResponse<any>>(`${this.apiUrl}/read-all`, {}).subscribe({
      next: () => {
        this.notifications.update(list =>
          list.map(n => ({ ...n, is_read: true }))
        );
        this.unreadCount.set(0);
      }
    });
  }

  /** Delete a notification */
  deleteNotification(id: number): void {
    this.http.delete<ApiResponse<any>>(`${this.apiUrl}/${id}`).subscribe({
      next: () => {
        const wasUnread = this.notifications().find(n => n.id === id && !n.is_read);
        this.notifications.update(list => list.filter(n => n.id !== id));
        if (wasUnread) {
          this.unreadCount.update(c => Math.max(0, c - 1));
        }
      }
    });
  }

  /** Connect to /ws/notifications for real-time push */
  private connectWs(): void {
    if (this.ws) return;
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      const notif: AppNotification = JSON.parse(event.data);
      if (notif.alert_type) {
        // Prepend to list, cap at 50
        this.notifications.update(list => [notif, ...list].slice(0, 50));
        if (!notif.is_read) {
          this.unreadCount.update(c => c + 1);
        }
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      const delay = Math.min(
        this.BASE_DELAY * Math.pow(2, this.reconnectAttempts),
        this.MAX_RECONNECT_DELAY
      );
      this.reconnectAttempts++;
      setTimeout(() => this.connectWs(), delay);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  ngOnDestroy(): void {
    this.ws?.close();
    this.ws = null;
  }
}
```

---

## Task 11: Frontend — Notification Dropdown Component

**Files:**
- Create: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.ts`
- Create: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.html`
- Create: `frontend/src/app/layout/default-layout/default-header/notification-dropdown/notification-dropdown.component.scss`

**Step 1: Create component TS**

```typescript
import { Component, ChangeDetectionStrategy, inject, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  BadgeComponent,
  DropdownComponent,
  DropdownItemDirective,
  DropdownMenuDirective,
  DropdownToggleDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { NotificationCenterService } from '../../../../core/services/notification-center.service';

@Component({
  selector: 'app-notification-dropdown',
  templateUrl: './notification-dropdown.component.html',
  styleUrl: './notification-dropdown.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    BadgeComponent,
    DropdownComponent,
    DropdownToggleDirective,
    DropdownMenuDirective,
    DropdownItemDirective,
    IconDirective,
    RouterLink,
  ],
})
export class NotificationDropdownComponent {
  readonly #notifService = inject(NotificationCenterService);
  readonly unreadCount = this.#notifService.unreadCount;
  readonly notifications = computed(() => this.#notifService.notifications().slice(0, 10));

  markAsRead(id: number): void {
    this.#notifService.markAsRead(id);
  }

  markAllRead(): void {
    this.#notifService.markAllRead();
  }

  timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'ora';
    if (mins < 60) return `${mins}m fa`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h fa`;
    const days = Math.floor(hours / 24);
    return `${days}g fa`;
  }
}
```

**Step 2: Create component HTML**

```html
<c-dropdown alignment="end" variant="nav-item">
  <button [caret]="false" cDropdownToggle class="notification-bell" aria-label="Notifiche">
    <svg cIcon name="cilBell" size="lg"></svg>
    @if (unreadCount() > 0) {
      <c-badge color="danger" shape="rounded-pill" class="notification-badge">
        {{ unreadCount() > 99 ? '99+' : unreadCount() }}
      </c-badge>
    }
  </button>
  <div cDropdownMenu class="notification-menu pt-0">
    <div class="notification-header d-flex align-items-center justify-content-between px-3 py-2">
      <span class="fw-semibold small">Notifiche</span>
      @if (unreadCount() > 0) {
        <button class="btn btn-link btn-sm p-0 text-decoration-none small"
          (click)="markAllRead()">
          Segna tutte lette
        </button>
      }
    </div>
    <div class="notification-list">
      @for (n of notifications(); track n.id) {
        <button cDropdownItem
          class="notification-item"
          [class.notification-item--unread]="!n.is_read"
          (click)="markAsRead(n.id)">
          <span class="notification-emoji">{{ n.emoji }}</span>
          <div class="notification-content">
            <div class="notification-title">{{ n.title }}</div>
            <div class="notification-time text-body-secondary">{{ timeAgo(n.created_at) }}</div>
          </div>
          @if (!n.is_read) {
            <span class="notification-dot"></span>
          }
        </button>
      } @empty {
        <div class="text-center py-4 text-body-secondary small">
          Nessuna notifica
        </div>
      }
    </div>
    <div class="notification-footer text-center border-top py-2">
      <a routerLink="/notifications" class="small text-decoration-none">
        Vedi tutte
      </a>
    </div>
  </div>
</c-dropdown>
```

**Step 3: Create component SCSS**

```scss
@use "palette" as *;

.notification-bell {
  position: relative;
  background: none;
  border: none;
  color: var(--cui-header-color);
  cursor: pointer;
  padding: 0.25rem;
}

.notification-badge {
  position: absolute;
  top: -4px;
  right: -6px;
  font-size: 0.625rem;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  padding: 0 4px;
}

.notification-menu {
  width: 360px;
  max-height: 480px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.notification-header {
  border-bottom: 1px solid var(--cui-border-color);
}

.notification-list {
  overflow-y: auto;
  max-height: 360px;
  flex: 1;
}

.notification-item {
  display: flex !important;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 1rem !important;
  white-space: normal !important;
  border-bottom: 1px solid var(--mantis-border-subtle, rgba(255,255,255,0.06));

  &--unread {
    background: rgba($mantis-green, 0.04);
  }
}

.notification-emoji {
  font-size: 1.25rem;
  flex-shrink: 0;
  line-height: 1.4;
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.notification-time {
  font-size: 0.6875rem;
  margin-top: 2px;
}

.notification-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: $mantis-neon;
  flex-shrink: 0;
  margin-top: 6px;
}

.notification-footer {
  border-top: 1px solid var(--cui-border-color);
}
```

---

## Task 12: Frontend — Wire Bell into Header

**Files:**
- Modify: `frontend/src/app/layout/default-layout/default-header/default-header.component.ts`
- Modify: `frontend/src/app/layout/default-layout/default-header/default-header.component.html`

**Step 1: Import NotificationDropdownComponent and NotificationCenterService**

In `default-header.component.ts`, add imports:
```typescript
import { NotificationDropdownComponent } from './notification-dropdown/notification-dropdown.component';
import { NotificationCenterService } from '../../../core/services/notification-center.service';
```

Add `NotificationDropdownComponent` to the `imports` array.

Add to the class:
```typescript
readonly #notifCenter = inject(NotificationCenterService);

constructor() {
  super();
  this.#notifCenter.init();
}
```

**Step 2: Add bell to header HTML**

In `default-header.component.html`, between the WS status `</c-nav-item>` and the vertical divider before theme toggle, insert:

```html
<div class="nav-item py-1">
  <div class="vr h-100 mx-2 text-body text-opacity-75"></div>
</div>
<!-- Notification Bell -->
<app-notification-dropdown />
```

---

## Task 13: Frontend — Notifications Page

**Files:**
- Create: `frontend/src/app/views/notifications/notifications.component.ts`
- Create: `frontend/src/app/views/notifications/notifications.component.html`
- Create: `frontend/src/app/views/notifications/notifications.component.scss`
- Create: `frontend/src/app/views/notifications/routes.ts`
- Modify: `frontend/src/app/app.routes.ts` (add route)
- Modify: `frontend/src/app/layout/default-layout/_nav.ts` (add nav item)

**Step 1: Create page component** (TS, HTML, SCSS + routes)

The notifications page should have:
- Filter row: alert_type select, severity select, epic select, "solo non lette" toggle
- KPI cards: total unread (per severity)
- Paginated table: emoji | title | message (truncated) | asset | severity badge | time | actions
- Actions: mark as read, delete
- Pagination controls

**Step 2: Add route in `app.routes.ts`**

After the `system-logs` route:
```typescript
{
  path: 'notifications',
  loadChildren: () => import('./views/notifications/routes').then(m => m.routes)
},
```

**Step 3: Add nav item in `_nav.ts`**

In the "Sistema" section, before "Impostazioni":
```typescript
{
  name: 'Notifiche',
  url: '/notifications',
  iconComponent: { name: 'cil-bell' },
  badge: { color: 'danger', text: '' }  // Updated dynamically? Or static for now
},
```

---

## Task 14: Build Verification + Tests

**Step 1: Run backend tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q --tb=short
```

**Step 2: Run frontend build**

```bash
cd frontend && npx ng build --configuration=development 2>&1 | tail -20
```

**Step 3: Apply migration and restart backend**

```bash
cd backend && .venv/Scripts/python.exe -m alembic upgrade head
```

---

## Parallel Execution Strategy

Tasks 1-9 (backend) and Tasks 10-13 (frontend) are **independent** and can run in parallel:

**Agent A (Backend):** Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
**Agent B (Frontend):** Tasks 10 → 11 → 12 → 13

Task 14 (verification) runs after both complete.

---

## File Summary

| File | Action | Task |
|------|--------|------|
| `backend/src/database/models.py` | Modify | 1 |
| `backend/alembic/versions/...add_notifications.py` | Create | 2 |
| `backend/src/database/repositories/notification_repository.py` | Create | 3 |
| `backend/src/database/repositories/__init__.py` | Modify | 3 |
| `backend/src/monitoring/alerting/in_app_channel.py` | Create | 4 |
| `backend/src/monitoring/alerting/alert_manager.py` | Modify | 5 |
| `backend/src/api/websocket.py` | Modify | 6 |
| `backend/src/api/routers/notifications.py` | Create | 7 |
| `backend/src/api/main.py` | Modify | 8 |
| `backend/tests/api/test_notifications.py` | Create | 9 |
| `frontend/src/app/core/models/notification.model.ts` | Create | 10 |
| `frontend/src/app/core/models/index.ts` | Modify | 10 |
| `frontend/src/app/core/services/notification-center.service.ts` | Create | 10 |
| `frontend/.../notification-dropdown/notification-dropdown.component.*` | Create | 11 |
| `frontend/.../default-header/default-header.component.*` | Modify | 12 |
| `frontend/src/app/views/notifications/*` | Create | 13 |
| `frontend/src/app/app.routes.ts` | Modify | 13 |
| `frontend/src/app/layout/default-layout/_nav.ts` | Modify | 13 |
