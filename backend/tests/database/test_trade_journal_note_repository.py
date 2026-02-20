"""Tests for TradeJournalNoteRepository."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.models import TradeJournalNote
from src.database.repositories.trade_journal_note_repository import (
    TradeJournalNoteRepository,
)


@pytest.fixture
def mock_session():
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session):
    """TradeJournalNoteRepository with mocked session."""
    return TradeJournalNoteRepository(mock_session)


def _make_note(epic="GOLD", ts="2026-02-19T10:30:00", notes="Test note"):
    """Create a TradeJournalNote model instance."""
    return TradeJournalNote(
        id=1,
        epic=epic,
        signal_timestamp=ts,
        notes=notes,
    )


def _mock_scalar_result(value):
    """Mock session.execute() result for scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(values):
    """Mock session.execute() result for scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result.scalars.return_value = scalars_mock
    return result


class TestGetBySignal:
    @pytest.mark.asyncio
    async def test_get_by_signal_found(self, repo, mock_session):
        note = _make_note()
        mock_session.execute.return_value = _mock_scalar_result(note)
        result = await repo.get_by_signal("GOLD", "2026-02-19T10:30:00")
        assert result is note
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_signal_not_found(self, repo, mock_session):
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await repo.get_by_signal("GOLD", "2026-02-19T10:30:00")
        assert result is None


class TestUpsertNote:
    @pytest.mark.asyncio
    async def test_upsert_note_create(self, repo, mock_session):
        """No existing note → create new one."""
        # get_by_signal returns None (not found)
        mock_session.execute.return_value = _mock_scalar_result(None)

        # Mock the create method (from BaseRepository)
        created_note = _make_note(notes="Nuova nota")
        with patch.object(repo, "create", new_callable=AsyncMock, return_value=created_note):
            result = await repo.upsert_note("GOLD", "2026-02-19T10:30:00", "Nuova nota")

        assert result.notes == "Nuova nota"
        assert result.epic == "GOLD"

    @pytest.mark.asyncio
    async def test_upsert_note_update(self, repo, mock_session):
        """Existing note → update in place."""
        existing = _make_note(notes="Vecchia nota")
        mock_session.execute.return_value = _mock_scalar_result(existing)

        result = await repo.upsert_note("GOLD", "2026-02-19T10:30:00", "Nota aggiornata")

        assert result.notes == "Nota aggiornata"
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(existing)


class TestDeleteNote:
    @pytest.mark.asyncio
    async def test_delete_note_existing(self, repo, mock_session):
        note = _make_note()
        mock_session.execute.return_value = _mock_scalar_result(note)
        result = await repo.delete_note("GOLD", "2026-02-19T10:30:00")
        assert result is True
        mock_session.delete.assert_awaited_once_with(note)

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, repo, mock_session):
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await repo.delete_note("GOLD", "2026-02-19T10:30:00")
        assert result is False
        mock_session.delete.assert_not_awaited()


class TestGetAllNotes:
    @pytest.mark.asyncio
    async def test_get_all_notes_empty(self, repo, mock_session):
        mock_session.execute.return_value = _mock_scalars_result([])
        result = await repo.get_all_notes()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_all_notes_with_data(self, repo, mock_session):
        notes = [
            _make_note("GOLD", "2026-02-19T10:30:00", "Nota 1"),
            _make_note("BTCUSD", "2026-02-19T11:00:00", "Nota 2"),
        ]
        mock_session.execute.return_value = _mock_scalars_result(notes)
        result = await repo.get_all_notes()
        assert len(result) == 2
        assert result["GOLD|2026-02-19T10:30:00"] == "Nota 1"
        assert result["BTCUSD|2026-02-19T11:00:00"] == "Nota 2"
