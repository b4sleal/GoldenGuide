"""Academic level (undergraduate / graduate) on WLU pages and courses, filled from calendar URLs.

Only Academic Calendar records get a level, read from the calendar's `cal` URL parameter
(1 = undergraduate, 3 = graduate, as the calendar home page lists them). Every other row stays NULL:
website pages such as tuition or important dates apply to every student. The calendar parse sets the
same values from then on (AcademicCalendarProfile.CALENDAR_LEVELS); the mapping is frozen here so
this revision stays reproducible if that mapping changes later.

Downgrade drops the columns: the values are derived from URLs, so nothing is lost.

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALENDAR_SITE = "academic_calendar_wlu"
CALENDAR_URL_PATTERN = "^https?://academic-calendar\\.wlu\\.ca/"
LEVEL_BY_CAL = {"1": "undergraduate", "3": "graduate"}
TABLES = ("wlu_pages", "courses")


def _cal_pattern(cal: str) -> str:
    """Matches a URL whose query has cal=<cal> (not cal=10, not xcal=1)."""
    return f"[?&]cal={cal}(&|$)"


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("academic_level", sa.String(length=16), nullable=True))
        op.create_index(op.f(f"ix_{table}_academic_level"), table, ["academic_level"], unique=False)

    for cal, level in LEVEL_BY_CAL.items():
        op.execute(
            sa.text(
                "UPDATE wlu_pages SET academic_level = :level "
                "WHERE site_name = :site AND url ~ :cal"
            ).bindparams(level=level, site=CALENDAR_SITE, cal=_cal_pattern(cal))
        )
        op.execute(
            sa.text(
                "UPDATE courses SET academic_level = :level "
                "WHERE calendar_url ~ :host AND calendar_url ~ :cal"
            ).bindparams(level=level, host=CALENDAR_URL_PATTERN, cal=_cal_pattern(cal))
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(op.f(f"ix_{table}_academic_level"), table_name=table)
        op.drop_column(table, "academic_level")
