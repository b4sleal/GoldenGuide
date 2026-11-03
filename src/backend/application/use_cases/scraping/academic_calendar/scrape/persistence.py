"""Parse a batch of stored calendar pages and upsert them as courses or wlu_pages rows.

Unknown subject codes block the batch (add them to wlu_lexicon.yml). Pages that cannot be parsed
are logged and skipped; they stay flagged for the next run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from backend.application.use_cases.scraping.academic_calendar.profile import (
    AcademicCalendarProfile,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.parse import (
    classify_calendar_url,
    parse_additional_course_information,
    parse_breadcrumbs,
    parse_course,
    parse_course_header,
    parse_department_contact,
    parse_page_content,
)
from backend.domain.entities.scraping import ScrapePageRead, ScrapePageUpdate
from backend.domain.entities.wlu.course import CourseCreate, CourseMetadata
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.wlu_pages import (
    AcademicCalendarType,
    WluPageCreate,
    WluPageMetadata,
)
from backend.domain.ports.jobs.compute import ComputeExecutor
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.profiles import WluLexicon

logger = structlog.get_logger()


@dataclass
class ParsedCalendarBatch:
    academic_records: list[WluPageCreate] = field(default_factory=list)
    course_payloads: list[CourseCreate] = field(default_factory=list)
    persisted_pages: list[ScrapePageRead] = field(default_factory=list)
    pages_with_blob: int = 0
    skipped_pages: int = 0


class AcademicCalendarPersistenceService:
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(
            self,
            school_db: SchoolDB,
            blob_storage: BlobStorage,
            lexicon_resolver: WluLexiconResolver,
            lexicon_profile: WluLexicon,
            profile: AcademicCalendarProfile,
            compute: ComputeExecutor,
    ) -> None:
        self.school_db = school_db
        self.blob_storage = blob_storage
        self.lexicon_resolver = lexicon_resolver
        self.lexicon_profile = lexicon_profile
        self.profile = profile
        self.compute = compute

    async def execute(self, pages: list[ScrapePageRead], academic_year: str) -> dict:
        blob_keys = [p.blob_key for p in pages if p.blob_key]
        blob_data_map = await self.blob_storage.download_many(blob_keys, max_concurrency=50)

        # Parsing is CPU-bound: run it off the event loop; I/O stays here.
        batch = await self.compute.run(
            parse_calendar_batch, pages, blob_data_map, academic_year, self.lexicon_resolver, self.lexicon_profile,
        )

        async with self.school_db.start() as repos:
            if batch.course_payloads:
                await repos.courses.upsert_courses(batch.course_payloads)

            if batch.academic_records:
                await repos.wlu_pages.upsert_wlu_pages(batch.academic_records)

            if batch.persisted_pages:
                await repos.scraping.update_scrape_pages(
                    page_ids=[page.id for page in batch.persisted_pages],
                    update_data=ScrapePageUpdate(needs_persistence=False),
                )

        summary = {
            "pages_seen": len(pages),
            "pages_with_blob": batch.pages_with_blob,
            "skipped_pages": batch.skipped_pages,
            "course_payloads": len(batch.course_payloads),
            "academic_records": len(batch.academic_records),
        }

        logger.info("academic_calendar_batch_processed", **summary)
        return summary


def parse_calendar_batch(
        pages: list[ScrapePageRead],
        blob_data_map: dict[str, bytes | None],  # None: the blob is missing; the page is skipped.
        academic_year: str,
        lexicon_resolver: WluLexiconResolver,
        lexicon_profile: WluLexicon,
) -> ParsedCalendarBatch:
    """Stored HTML -> course and wlu_pages records.

    Pure and module-level (not a method), so it can run in another process: it reads only its
    arguments, and the lexicons are read-only.
    """
    batch = ParsedCalendarBatch()

    # ---------------------------------------------------------
    # Track tuples of (Subject Code, Raw Description)
    # ---------------------------------------------------------
    unmapped_course_codes: set[tuple[str, str]] = set()

    for page in pages:
        if not page.blob_key:
            batch.skipped_pages += 1
            continue

        raw_bytes = blob_data_map.get(page.blob_key)
        if not raw_bytes:
            batch.skipped_pages += 1
            continue

        batch.pages_with_blob += 1
        html_text = raw_bytes.decode("utf-8", errors="ignore")

        page_text, title, external_links = parse_page_content(html_text, page.url)
        department_contact = parse_department_contact(html_text, page.url, external_links)
        additional = parse_additional_course_information(html_text, page.url, external_links)

        # Extract the RAW text first to use for logging
        # The last crumb is the page itself; on a faculty's own page it is the only crumb.
        raw_faculty, raw_departments, raw_current = parse_breadcrumbs(html_text)

        # Then resolve them for the database
        faculty = lexicon_resolver.resolve_faculty(raw_faculty)
        # Canonical names keep departments the same across sources (calendar, LORIS); unlisted ones keep theirs.
        departments = [lexicon_resolver.department_name(d) for d in raw_departments]

        is_faculty_crumb = not raw_departments and raw_current == raw_faculty
        record_type = classify_calendar_url(page.url, faculty, departments, is_faculty_crumb, lexicon_profile)

        academic_level = AcademicCalendarProfile.academic_level(page.url)
        if academic_level is None:
            # Stored without a level (as if it applied to every student) until CALENDAR_LEVELS lists it.
            logger.warning(
                "academic_calendar_level_unknown", url=page.url, cal=AcademicCalendarProfile.calendar_param(page.url),
            )

        if not title.strip() or not page_text.strip():
            logger.warning(
                "academic_calendar_empty_page_skipped",
                url=page.url,
                record_type=record_type.value,
                empty_title=not title.strip(),
                empty_content=not page_text.strip(),
            )
            batch.skipped_pages += 1
            continue

        if record_type == AcademicCalendarType.COURSE:
            course_header = parse_course_header(html_text)
            if not course_header:
                logger.warning("academic_calendar_course_header_unparsed", url=page.url)
                batch.skipped_pages += 1
                continue

            subject_code, course_number, parsed_title, credit_json = course_header

            canonical_subject = lexicon_resolver.resolve_subject(subject_code)
            if not canonical_subject:
                # Capture the raw description from the breadcrumb if available
                raw_desc = raw_departments[-1] if raw_departments else "Unknown Description"
                unmapped_course_codes.add((subject_code, raw_desc))
                continue

            parsed_course_text = parse_course(html_text, page.url, external_links)

            if not parsed_course_text:
                batch.skipped_pages += 1
                continue
            batch.persisted_pages.append(page)
            batch.course_payloads.append(
                CourseCreate(
                    academic_year=academic_year,
                    campus="Waterloo",
                    institution="WLU",
                    subject=canonical_subject,
                    subject_code=subject_code,
                    course_number=course_number,
                    academic_level=academic_level,
                    title=parsed_title,
                    description=parsed_course_text,
                    calendar_url=page.url,
                    prereq=additional["prereq"],
                    coreq=additional["coreq"],
                    exclusions=additional["exclusions"],
                    notes=additional["notes"],
                    content_hash=page.content_hash,
                    credit_min=credit_json.get("min"),
                    credit_max=credit_json.get("max"),
                    credit_unit=credit_json.get("unit"),
                    metadata_json=CourseMetadata(
                        department_contact=department_contact,
                        external_links=external_links,
                        faculty=faculty,
                        departments=departments,
                    ),
                )
            )
            continue

        if record_type == AcademicCalendarType.DEPARTMENT:
            title = lexicon_resolver.department_name(title)

        batch.persisted_pages.append(page)
        batch.academic_records.append(
            WluPageCreate(
                site_name=AcademicCalendarProfile.SITE_NAME,
                version=academic_year,
                url=page.url,
                content_hash=page.content_hash,
                record_type=record_type,
                academic_level=academic_level,
                title=title,
                content=page_text,
                metadata_json=WluPageMetadata(
                    department_contact=department_contact,
                    external_links=external_links,
                ),
            )
        )

    if unmapped_course_codes:
        # Format nicely for the error log
        unmapped_list = [f"[{code}] '{desc}'" for code, desc in unmapped_course_codes]
        raise ValueError(
            f"Strict Gatekeeper Block: Unmapped Calendar Subject Codes found: {unmapped_list}. "
            f"Please add them to wlu_lexicon.yml and retry the ingestion batch."
        )

    return batch
