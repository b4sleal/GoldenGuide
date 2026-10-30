"""Academic-year arithmetic for WLU."""
from datetime import datetime, timezone


def get_current_academic_year(reference_date: datetime | None = None) -> str:
    """Return the WLU academic year ("YYYY/YYYY") that contains `reference_date`.

    The academic year starts in September (Fall term):
        March 15, 2026 -> "2025/2026"
        Sept 01, 2026  -> "2026/2027"

    Defaults to now (UTC). Pass `reference_date` in tests for deterministic results.
    """
    dt = reference_date or datetime.now(timezone.utc)

    # January-August still belong to the year that started the previous September.
    if dt.month < 9:
        return f"{dt.year - 1}/{dt.year}"
    return f"{dt.year}/{dt.year + 1}"
