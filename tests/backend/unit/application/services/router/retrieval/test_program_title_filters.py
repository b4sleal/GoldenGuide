"""SQL compilation tests: AND/OR and injection-safe literal matching."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.ports.repositories.filters import WluPageFilter
from backend.infra.persistence.db.school.filters import WluPageFilterTranslator
from backend.infra.persistence.db.school.school_tables import WluPage


def compile_where(operator):
    stmt = WluPageFilterTranslator.apply(
        select(WluPage),
        WluPageFilter(
            record_type=AcademicCalendarType.PROGRAM,
            title_terms=["Biology", "Chemistry"],
            title_operator=operator,
        ),
    )
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_multi_department_and():
    assert " AND " in compile_where("all")


def test_multi_department_or():
    assert " OR " in compile_where("any")


def test_fuzzy_user_text_never_becomes_sql():
    stmt = WluPageFilterTranslator.apply(
        select(WluPage),
        WluPageFilter(title_terms=["x%' OR true --"]),
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "OR true" not in sql


def test_record_ids_become_an_in_clause():
    stmt = WluPageFilterTranslator.apply(select(WluPage), WluPageFilter(record_ids=[11, 12]))
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "wlu_pages.id IN" in sql
