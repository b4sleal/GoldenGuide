"""WLU academic terms: turn what a student says ("winter", "fall 2027", "next year") into LORIS term codes.

Term codes are YYYYMM, where the month marks the term's start: 01 Winter, 05 Spring/Summer, 09 Fall.
All "relative" logic (current term, next occurrence of a season) lives here, so every caller
interprets terms the same way. These are WLU business rules with no I/O, hence the domain layer.
"""
from collections.abc import Callable, Iterable
from datetime import date, datetime
from types import MappingProxyType
from zoneinfo import ZoneInfo

from backend.domain.entities.wlu.academic_calendar import Season

type Clock = Callable[[], date]


def institution_clock(timezone: ZoneInfo) -> Clock:
    """Today's date where the institution is (a term starts on a local date, not a UTC one)."""
    return lambda: datetime.now(timezone).date()


class AcademicTermResolver:
    """Resolves WLU academic terms relative to an injected "today".

    Every relative answer reads the clock, so tests and the router prompt agree on one date. The
    composition root supplies institution_clock(<configured timezone>).
    """

    # LORIS term-code suffix per season: the month the term starts.
    TERM_SUFFIXES = MappingProxyType({
        Season.WINTER: "01",
        Season.SPRING: "05",
        Season.INTERSESSION: "05",
        Season.SUMMER: "05",
        Season.FALL: "09",
    })

    # One season per distinct term code, in calendar order (used when only a year is given).
    TERMS_IN_YEAR = (Season.WINTER, Season.SPRING, Season.FALL)

    def __init__(self, clock: Clock):
        self.clock = clock

    def today(self) -> date:
        return self.clock()

    def resolve(self, terms: Iterable[str] | None, years: Iterable[int] | None) -> list[str]:
        """Turn the router's term/year filters into term codes, relative to today.

            terms + years   every combination              ("winter", 2027)  -> 202701
            terms only      next occurrence of each term   "winter" in Oct 2026 -> 202701
            years only      every term in each year        2027 -> 202701, 202705, 202709
            neither         the current term

        Duplicates are removed in order (spring/summer/intersession share one code).
        """
        terms, years = list(terms or []), list(years or [])

        if terms and years:
            codes = [self.encode(term, year) for year in years for term in terms]
        elif terms:
            codes = [self.upcoming(term) for term in terms]
        elif years:
            codes = [self.encode(term, year) for year in years for term in self.TERMS_IN_YEAR]
        else:
            codes = [self.current()]

        return list(dict.fromkeys(codes))

    def upcoming(self, term: str) -> str:
        """The next time `term` happens, counting a term that is already in progress.

        In October 2026 (Fall in progress): fall -> 202609, winter -> 202701, spring -> 202705.
        Students asking "is CP220 offered in winter?" in the fall mean the coming winter.
        """
        current = self.current()
        year = int(current[:4])
        this_year = self.encode(term, year)
        # Codes are YYYYMM strings, so string order equals chronological order.
        return this_year if this_year >= current else self.encode(term, year + 1)

    def shift(self, offset: int) -> tuple[Season, int]:
        """(season, year) `offset` terms from the current one: 1 is "next term", -1 "last term".

        Steps through the distinct registration terms (winter, spring, fall), so in October 2026
        shift(1) is (WINTER, 2027) and shift(2) is (SPRING, 2027).
        """
        current = self.current()
        season = next(term for term in self.TERMS_IN_YEAR if self.TERM_SUFFIXES[term] == current[4:])
        position = int(current[:4]) * len(self.TERMS_IN_YEAR) + self.TERMS_IN_YEAR.index(season) + offset
        year, index = divmod(position, len(self.TERMS_IN_YEAR))
        return self.TERMS_IN_YEAR[index], year

    def current(self) -> str:
        """The active registration term as YYYYMM: Jan-Apr Winter, May-Aug Spring, Sep-Dec Fall."""
        today = self.clock()

        if today.month <= 4:
            term = Season.WINTER
        elif today.month <= 8:
            term = Season.SPRING
        else:
            term = Season.FALL

        return self.encode(term, today.year)

    # Each term spans four months starting at its code's month (01, 05, 09).
    TERM_MONTHS = 4

    def past_midpoint(self) -> bool:
        """Whether today is in the second half of the current term (e.g. Fall from November on).

        Past the midpoint, students start planning the next term, so date questions cover both.
        """
        today = self.clock()
        start_month = int(self.current()[4:])
        return (today.month - start_month) * 2 >= self.TERM_MONTHS

    @staticmethod
    def label(season: Season, year: int) -> str:
        return f"{season.value.title()} {year}"

    @classmethod
    def encode(cls, term: str, year: int) -> str:
        """Convert an academic term into its registration term code. Pure: no notion of today."""
        try:
            season = Season(term.lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported academic term: {term}") from exc

        if not 1000 <= year <= 9999:
            raise ValueError(f"Invalid academic year: {year}")

        return f"{year}{cls.TERM_SUFFIXES[season]}"
