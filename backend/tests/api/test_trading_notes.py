"""Tests for Trade Journal Notes API (GET/PUT /api/trading/signals/notes)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_journal_note_repo
from src.api.main import app


@pytest.fixture
def mock_note_repo():
    """Mock TradeJournalNoteRepository."""
    repo = AsyncMock()
    repo.get_all_notes = AsyncMock(return_value={})
    repo.upsert_note = AsyncMock()
    repo.delete_note = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def notes_client(client, mock_note_repo):
    """Client with journal note repo override."""
    app.dependency_overrides[get_journal_note_repo] = lambda: mock_note_repo
    yield client
    # conftest.client fixture clears all overrides on teardown


class TestListSignalNotes:
    def test_get_signal_notes_empty(self, notes_client, mock_note_repo):
        mock_note_repo.get_all_notes.return_value = {}
        resp = notes_client.get("/api/trading/signals/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {}

    def test_get_signal_notes_with_data(self, notes_client, mock_note_repo):
        mock_note_repo.get_all_notes.return_value = {
            "GOLD|2026-02-19T10:30:00": "Buon segnale, trend forte",
            "BTCUSD|2026-02-19T11:00:00": "Troppo volatile",
        }
        resp = notes_client.get("/api/trading/signals/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert "GOLD|2026-02-19T10:30:00" in body["data"]
        assert body["data"]["GOLD|2026-02-19T10:30:00"] == "Buon segnale, trend forte"

    def test_get_signal_notes_when_repo_none(self, client):
        """Graceful degradation: no DB → return empty dict."""
        app.dependency_overrides[get_journal_note_repo] = lambda: None
        resp = client.get("/api/trading/signals/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {}

    def test_get_signal_notes_db_error(self, notes_client, mock_note_repo):
        """DB exception → catch, log, return empty dict."""
        mock_note_repo.get_all_notes.side_effect = Exception("Connection lost")
        resp = notes_client.get("/api/trading/signals/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {}


class TestUpsertSignalNote:
    def test_upsert_signal_note_create(self, notes_client, mock_note_repo):
        note_obj = MagicMock()
        note_obj.epic = "GOLD"
        note_obj.signal_timestamp = "2026-02-19T10:30:00"
        note_obj.notes = "Ottimo setup"
        note_obj.updated_at = None
        mock_note_repo.upsert_note.return_value = note_obj

        resp = notes_client.put(
            "/api/trading/signals/notes",
            json={
                "epic": "GOLD",
                "signal_timestamp": "2026-02-19T10:30:00",
                "notes": "Ottimo setup",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["epic"] == "GOLD"
        assert body["data"]["notes"] == "Ottimo setup"
        mock_note_repo.upsert_note.assert_awaited_once_with(
            epic="GOLD",
            signal_timestamp="2026-02-19T10:30:00",
            notes="Ottimo setup",
        )

    def test_upsert_signal_note_empty_deletes(self, notes_client, mock_note_repo):
        """Empty notes string triggers delete."""
        resp = notes_client.put(
            "/api/trading/signals/notes",
            json={
                "epic": "GOLD",
                "signal_timestamp": "2026-02-19T10:30:00",
                "notes": "   ",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["deleted"] is True
        mock_note_repo.delete_note.assert_awaited_once_with(
            "GOLD", "2026-02-19T10:30:00"
        )

    def test_upsert_signal_note_strips_whitespace(self, notes_client, mock_note_repo):
        note_obj = MagicMock()
        note_obj.epic = "BTCUSD"
        note_obj.signal_timestamp = "2026-02-19T11:00:00"
        note_obj.notes = "Nota con spazi"
        note_obj.updated_at = None
        mock_note_repo.upsert_note.return_value = note_obj

        resp = notes_client.put(
            "/api/trading/signals/notes",
            json={
                "epic": "BTCUSD",
                "signal_timestamp": "2026-02-19T11:00:00",
                "notes": "  Nota con spazi  ",
            },
        )
        assert resp.status_code == 200
        mock_note_repo.upsert_note.assert_awaited_once_with(
            epic="BTCUSD",
            signal_timestamp="2026-02-19T11:00:00",
            notes="Nota con spazi",
        )

    def test_upsert_signal_note_missing_fields(self, notes_client):
        """Missing required fields → 422 validation error."""
        resp = notes_client.put(
            "/api/trading/signals/notes",
            json={"epic": "GOLD"},
        )
        assert resp.status_code == 422

    def test_upsert_signal_note_when_repo_none(self, client):
        """No DB → return 503."""
        app.dependency_overrides[get_journal_note_repo] = lambda: None
        resp = client.put(
            "/api/trading/signals/notes",
            json={
                "epic": "GOLD",
                "signal_timestamp": "2026-02-19T10:30:00",
                "notes": "Test",
            },
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["success"] is False
        assert "not available" in body["error"].lower()
