"""Which terms a dates-and-deadlines answer covers, decided in code so the answer model does no date math.

WLU website pages are live: an "Important Dates" page lists the current academic year, not one term.
When a student asks for dates without naming a term, the answer covers the current term; past its
midpoint it covers the rest of the current term and the next one (in December, January matters more
than September).
"""
from backend.domain.entities.wlu.academic_term import AcademicTermResolver


def terms_to_cover(resolver: AcademicTermResolver) -> str:
    """The answer prompt's scope line, e.g. "Fall 2026 (the whole term)"."""
    current = resolver.label(*resolver.shift(0))
    if not resolver.past_midpoint():
        return f"{current} (the whole term)"

    upcoming = resolver.label(*resolver.shift(1))
    return (
        f"{current} (dates from today on; say that earlier {current} dates have passed and can be "
        f"listed on request), then {upcoming}"
    )
