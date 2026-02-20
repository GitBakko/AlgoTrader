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

    def test_list_notifications(self, client, mock_notification):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.get_list.return_value = ([mock_notification], 1)
            mock_get_repo.return_value = repo_instance

            response = client.get("/api/notifications/")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["data"]["notifications"]) == 1
            assert data["data"]["total"] == 1
            assert data["data"]["notifications"][0]["alert_type"] == "TRADE_OPENED"

    def test_unread_count(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.get_unread_count.return_value = 5
            mock_get_repo.return_value = repo_instance

            response = client.get("/api/notifications/unread-count")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["count"] == 5

    def test_mark_as_read(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.mark_as_read.return_value = True
            mock_get_repo.return_value = repo_instance

            response = client.put("/api/notifications/1/read")
            assert response.status_code == 200

    def test_mark_as_read_not_found(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.mark_as_read.return_value = False
            mock_get_repo.return_value = repo_instance

            response = client.put("/api/notifications/999/read")
            assert response.status_code == 404

    def test_mark_all_read(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.mark_all_read.return_value = 3
            mock_get_repo.return_value = repo_instance

            response = client.put("/api/notifications/read-all")
            assert response.status_code == 200
            assert response.json()["data"]["count"] == 3

    def test_delete_notification(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.delete_one.return_value = True
            mock_get_repo.return_value = repo_instance

            response = client.delete("/api/notifications/1")
            assert response.status_code == 200

    def test_delete_notification_not_found(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            repo_instance = AsyncMock()
            repo_instance.delete_one.return_value = False
            mock_get_repo.return_value = repo_instance

            response = client.delete("/api/notifications/999")
            assert response.status_code == 404

    def test_list_no_db(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            mock_get_repo.return_value = None

            response = client.get("/api/notifications/")
            assert response.status_code == 503

    def test_unread_count_no_db(self, client):
        with patch(
            "src.api.routers.notifications._get_repo"
        ) as mock_get_repo:
            mock_get_repo.return_value = None

            response = client.get("/api/notifications/unread-count")
            assert response.status_code == 200
            assert response.json()["data"]["count"] == 0
