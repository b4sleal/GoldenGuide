"""Academic Calendar courses -> Evidence (prompt text at three detail levels, plus a table row). Pure functions."""
import json

from backend.application.services.router.evidence.academic_links import (
    AcademicLinkResolver,
)
from backend.application.services.router.evidence.fields import field_lines
from backend.domain.entities.retrieval import Evidence, TableRow
from backend.domain.entities.wlu.course import CourseRead

RECORD = "Academic Calendar record"


def course_evidence(course: CourseRead, primary: bool) -> Evidence:
    """Evidence for one catalog course; scraper link placeholders become real URLs in every field."""
    code = f"{course.subject_code}{course.course_number}"

    metadata = course.metadata_json
    links = metadata.external_links if metadata else None

    def resolve(value: str | None) -> str:
        return AcademicLinkResolver.resolve(
            content=value,
            external_links=links,
        )

    credits = f"Credits: {json.dumps(course.credit_summary())}"
    requirements = {
        "Prerequisites": resolve(course.prereq),
        "Corequisites": resolve(course.coreq),
        "Exclusions": resolve(course.exclusions),
    }

    present, absent = field_lines({
        "Title": course.title,
        "Subject": course.subject,
        "Description": resolve(course.description),
        **requirements,
        "Notes": resolve(course.notes),
    }, RECORD)
    content = "\n".join([f"Course: {code}", f"Academic year: {course.academic_year}", *present, credits, *absent])

    present, absent = field_lines({"Title": course.title, **requirements}, RECORD)
    compact_content = "\n".join([
        f"Course: {code}",
        f"Academic year: {course.academic_year}",
        "Description summary: Not available",
        *present,
        credits,
        *absent,
    ])

    present, absent = field_lines({"Title": course.title}, RECORD)
    minimal_content = "\n".join([f"Course: {code}", f"Academic year: {course.academic_year}", *present, credits, *absent])

    # One table per subject, so subject listings ("computer science courses") render as rows
    # of exact database values instead of the model retyping them (see evidence_tables.py).
    credit = course.credit_summary()
    table_row = TableRow(
        group=f"{course.subject or course.subject_code} courses — {course.academic_year}",
        cells={
            "Course": code,
            "Title": course.title or "—",
            "Credits": str(credit["max"]) if credit.get("max") is not None else "—",
        },
    )

    return Evidence(
        table_row=table_row,
        source_id=f"course:{course.id}",
        title=f"{code} — {course.title or 'Course'}",
        url=course.calendar_url or "",
        content=content,
        compact_content=compact_content,
        minimal_content=minimal_content,
        primary=primary,
    )
