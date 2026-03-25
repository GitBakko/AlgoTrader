"""
Broker error parser: transforms raw Capital.com error messages into structured,
human-readable format with Italian localization.
"""

import re
from dataclasses import dataclass, asdict


# Day name mapping: English → Italian abbreviation
_DAY_IT = {
    "Mon": "Lun", "Tue": "Mar", "Wed": "Mer",
    "Thu": "Gio", "Fri": "Ven", "Sat": "Sab", "Sun": "Dom",
}


@dataclass
class ParsedBrokerError:
    error_type: str          # "market_closed", "insufficient_funds", "rate_limit", etc.
    summary: str             # Short message in Italian
    details: str | None      # Extra details (e.g. timetable)
    market_hours: dict | None  # {"Mon": "09:00-01:00", ...} if available
    raw: str                 # Original error message

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_timetable(raw: str) -> tuple[str | None, dict | None]:
    """
    Parse Capital.com timetable string into human-readable format.

    Input example:
      "UTC; Mon 09:00 -; Tue - 01:00, 09:00 -; Wed - 01:00, 09:00 -; ..."
    Returns:
      ("Lun-Gio 09:00-01:00, Ven 09:00-22:00 (UTC)", {"Mon": "09:00-", ...})
    """
    match = re.search(r"Timetable in place:\s*(.*?)\.?\s*$", raw, re.IGNORECASE)
    if not match:
        return None, None

    timetable_str = match.group(1).strip().rstrip(".")
    # Extract timezone (first segment before ';')
    parts = [p.strip() for p in timetable_str.split(";") if p.strip()]
    if not parts:
        return None, None

    tz = parts[0] if not any(d in parts[0] for d in _DAY_IT) else "UTC"
    day_parts = parts[1:] if tz == parts[0] else parts

    hours_map: dict[str, str] = {}
    for part in day_parts:
        # Match patterns like "Mon 09:00 -" or "Tue - 01:00, 09:00 -"
        day_match = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(.*)", part, re.IGNORECASE)
        if day_match:
            day = day_match.group(1)
            times = day_match.group(2).strip()
            hours_map[day] = times

    if not hours_map:
        return timetable_str, None

    # Build compact summary: group consecutive days with same hours
    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    available_days = [(d, hours_map[d]) for d in days_order if d in hours_map]

    groups: list[tuple[list[str], str]] = []
    for day, hours in available_days:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    summary_parts = []
    for days, hours in groups:
        if len(days) > 1:
            day_range = f"{_DAY_IT.get(days[0], days[0])}-{_DAY_IT.get(days[-1], days[-1])}"
        else:
            day_range = _DAY_IT.get(days[0], days[0])
        # Clean up hours format: "- 01:00, 09:00 -" → "09:00-01:00"
        clean_hours = hours.replace(" ", "").replace(",-", " / ").rstrip("-").lstrip("-")
        if clean_hours:
            summary_parts.append(f"{day_range} {clean_hours}")
        else:
            summary_parts.append(day_range)

    summary = ", ".join(summary_parts)
    if tz:
        summary += f" ({tz})"
    return summary, hours_map


def parse_broker_error(error_message: str, epic: str | None = None) -> ParsedBrokerError:
    """
    Parse a Capital.com broker error into a structured, human-readable format.

    Args:
        error_message: Raw error message from broker
        epic: Optional epic code for context

    Returns:
        ParsedBrokerError with Italian summary, details, and raw message
    """
    msg = str(error_message).strip()
    msg_lower = msg.lower()
    label = epic or "Asset"

    # --- Market closed ---
    if "currently closed" in msg_lower or "timetable in place" in msg_lower:
        timetable_summary, hours_map = _parse_timetable(msg)
        summary = f"{label} è attualmente chiuso"
        details = f"Orario di trading: {timetable_summary}" if timetable_summary else None
        return ParsedBrokerError(
            error_type="market_closed",
            summary=summary,
            details=details,
            market_hours=hours_map,
            raw=msg,
        )

    # --- Insufficient funds ---
    if "insufficient" in msg_lower and "fund" in msg_lower:
        return ParsedBrokerError(
            error_type="insufficient_funds",
            summary=f"Fondi insufficienti per {label}",
            details="Il saldo del conto non è sufficiente per aprire questa posizione.",
            market_hours=None,
            raw=msg,
        )

    # --- Rate limit ---
    if "rate" in msg_lower and "limit" in msg_lower:
        return ParsedBrokerError(
            error_type="rate_limit",
            summary="Limite richieste superato",
            details="Troppe richieste al broker. Riprova tra qualche secondo.",
            market_hours=None,
            raw=msg,
        )

    # --- Invalid stop-loss / take-profit ---
    if "stoploss" in msg_lower or "takeprofit" in msg_lower:
        val_match = re.search(r":\s*([\d.]+)", msg)
        val_info = f" (limit: {val_match.group(1)})" if val_match else ""
        is_sl = "stoploss" in msg_lower
        level_type = "Stop-Loss" if is_sl else "Take-Profit"
        return ParsedBrokerError(
            error_type="invalid_stops",
            summary=f"{level_type} non valido per {label}{val_info}",
            details=f"Il {level_type} è troppo vicino al prezzo corrente.",
            market_hours=None,
            raw=msg,
        )

    # --- Minimum position size ---
    if (
        ("minimum" in msg_lower and "size" in msg_lower)
        or ("minvalue" in msg_lower and "size" in msg_lower)
        or "error.invalid.size" in msg_lower
    ):
        # Try to extract the minimum size value
        size_match = re.search(r"minimum.*?size.*?(\d+[\.\d]*)", msg_lower)
        size_info = f" (min: {size_match.group(1)})" if size_match else ""
        return ParsedBrokerError(
            error_type="min_size",
            summary=f"Size troppo piccola per {label}{size_info}",
            details="La dimensione calcolata è inferiore al minimo consentito dal broker.",
            market_hours=None,
            raw=msg,
        )

    # --- Invalid market ---
    if "invalid" in msg_lower and ("market" in msg_lower or "epic" in msg_lower):
        return ParsedBrokerError(
            error_type="invalid_market",
            summary=f"Mercato {label} non valido o non disponibile",
            details=None,
            market_hours=None,
            raw=msg,
        )

    # --- Max positions ---
    if "maximum" in msg_lower and "position" in msg_lower:
        return ParsedBrokerError(
            error_type="max_positions",
            summary="Numero massimo di posizioni raggiunto",
            details="Chiudi una posizione esistente prima di aprirne una nuova.",
            market_hours=None,
            raw=msg,
        )

    # --- Generic order rejected ---
    if "reject" in msg_lower:
        # Extract reason after "Rejected." or use full message
        reason_match = re.search(r"rejected\.?\s*(.*)", msg, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else msg
        summary = f"Ordine {label} rifiutato"
        details = reason[:200] if reason and reason.lower() != "unknown rejection" else None
        return ParsedBrokerError(
            error_type="rejected",
            summary=summary,
            details=details,
            market_hours=None,
            raw=msg,
        )

    # --- Capital.com errorCode format: "error.xxx.yyy.zzz" ---
    error_code_match = re.search(r"error\.(\w+(?:\.\w+)*)", msg_lower)
    if error_code_match:
        code = error_code_match.group(0)
        return ParsedBrokerError(
            error_type="broker_error_code",
            summary=f"Errore broker per {label}: {code}",
            details=None,
            market_hours=None,
            raw=msg,
        )

    # --- Fallback: unknown error ---
    summary = msg[:100] + ("..." if len(msg) > 100 else "")
    return ParsedBrokerError(
        error_type="unknown",
        summary=f"Errore broker per {label}",
        details=summary if len(msg) > 50 else None,
        market_hours=None,
        raw=msg,
    )
