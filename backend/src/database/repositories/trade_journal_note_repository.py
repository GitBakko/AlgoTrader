"""
Trade journal note repository for user annotations on signals.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import TradeJournalNote
from src.database.repository import BaseRepository


class TradeJournalNoteRepository(BaseRepository[TradeJournalNote]):
    """Repository for trade journal notes."""

    def __init__(self, session: AsyncSession):
        super().__init__(TradeJournalNote, session)

    async def get_by_signal(self, epic: str, signal_timestamp: str) -> TradeJournalNote | None:
        """Get note for a specific signal."""
        result = await self.session.execute(
            select(TradeJournalNote)
            .where(TradeJournalNote.epic == epic)
            .where(TradeJournalNote.signal_timestamp == signal_timestamp)
        )
        return result.scalar_one_or_none()

    async def upsert_note(self, epic: str, signal_timestamp: str, notes: str) -> TradeJournalNote:
        """Create or update a note for a signal."""
        existing = await self.get_by_signal(epic, signal_timestamp)
        if existing:
            existing.notes = notes
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        note = TradeJournalNote(epic=epic, signal_timestamp=signal_timestamp, notes=notes)
        return await self.create(note)

    async def delete_note(self, epic: str, signal_timestamp: str) -> bool:
        """Delete a note for a signal."""
        existing = await self.get_by_signal(epic, signal_timestamp)
        if existing:
            await self.session.delete(existing)
            return True
        return False

    async def get_all_notes(self) -> dict[str, str]:
        """Get all notes as a dict keyed by 'epic|timestamp'."""
        result = await self.session.execute(select(TradeJournalNote))
        notes = {}
        for note in result.scalars().all():
            key = f"{note.epic}|{note.signal_timestamp}"
            notes[key] = note.notes
        return notes
