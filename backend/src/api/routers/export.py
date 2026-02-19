"""
Export API router.
Generates CSV downloads for positions.
"""

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from loguru import logger

from src.api.dependencies import get_position_repo

router = APIRouter()

MAX_EXPORT_ROWS = 10_000


@router.get("/positions/csv")
async def export_closed_positions_csv(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    close_reason: str | None = Query(default=None),
    epic: str | None = Query(default=None),
    position_repo=Depends(get_position_repo),
):
    """Export closed positions as CSV file."""
    if position_repo is None:
        return _empty_positions_csv()

    from_dt = datetime.fromisoformat(date_from) if date_from else None
    to_dt = datetime.fromisoformat(date_to) if date_to else None

    positions, total = await position_repo.get_closed_positions(
        limit=MAX_EXPORT_ROWS,
        offset=0,
        date_from=from_dt,
        date_to=to_dt,
        close_reason=close_reason,
        epic=epic,
    )

    logger.info(f"CSV export: {len(positions)} closed positions (total: {total})")

    output = io.StringIO()
    # BOM for Excel UTF-8 compatibility
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "Deal ID", "Epic", "Direction", "Size", "Entry Price", "Exit Price",
        "P&L", "Stop Loss", "Take Profit", "Close Reason",
        "Opened At", "Closed At", "Duration (min)",
    ])

    for p in positions:
        duration = None
        if p.opened_at and p.closed_at:
            duration = int((p.closed_at - p.opened_at).total_seconds() / 60)
        writer.writerow([
            p.deal_id,
            p.epic,
            p.direction,
            float(p.size),
            float(p.entry_price),
            float(p.current_price) if p.current_price else "",
            float(p.profit_loss) if p.profit_loss else "",
            float(p.stop_loss) if p.stop_loss else "",
            float(p.take_profit) if p.take_profit else "",
            p.close_reason or "",
            p.opened_at.isoformat() if p.opened_at else "",
            p.closed_at.isoformat() if p.closed_at else "",
            duration if duration is not None else "",
        ])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"mantis_positions_{timestamp}.csv"

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _empty_positions_csv() -> StreamingResponse:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Deal ID", "Epic", "Direction", "Size", "Entry Price", "Exit Price",
        "P&L", "Stop Loss", "Take Profit", "Close Reason",
        "Opened At", "Closed At", "Duration (min)",
    ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="mantis_positions_empty.csv"'
        },
    )
