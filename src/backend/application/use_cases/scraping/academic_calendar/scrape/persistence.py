"""Parse a batch of stored calendar pages and upsert them as courses or wlu_pages rows.

Unknown subject codes block the batch (add them to wlu_lexicon.yml). Pages that cannot be parsed
are logged and skipped; they stay flagged for the next run.
"""
from __future__ import annotations
import structlog

from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.application.use_cases.scraping.academic_calendar.profile import AcademicCalendarProfile
from backend.application.use_cases.scraping.academic_calendar.scrape.parse import (
    classify_calendar_url, parse_breadcrumbs, parse_course,
    parse_course_header, parse_department_contact, parse_page_content, parse_additional_course_information,
)
from backend.domain.entities.wlu.course import CourseCreate, CourseMetadata
from backend.domain.entities.scraping import ScrapePageRead, ScrapePageUpdate
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageCreate, WluPageMetadata
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.profiles import WluLexicon

logger = structlog.get_logger()

class AcademicCalendarPersistenceService:
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(
            self,
            school_db: SchoolDB,
            blob_storage: BlobStorage,
            lexicon_resolver: WluLexiconResolver,
            lexicon_profile: WluLexicon,
            profile: AcademicCalendarProfile,
    ) -> None:
        self.school_db = school_db
        self.blob_storage = blob_storage
        self.lexicon_resolver = lexicon_resolver
        self.lexicon_profile = lexicon_profile
        self.profile = profile

    async def execute(self, pages: list[ScrapePageRead], academic_year: str) -> dict:
        all_academic_records: list[WluPageCreate] = []
        all_course_payloads: list[CourseCreate] = []

        pages_with_blob = 0
        skipped_pages = 0

        blob_keys = [p.blob_key for p in pages if p.blob_key]
        blob_data_map = await self.blob_storage.download_many(blob_keys, max_concurrency=50)

        # ---------------------------------------------------------
        # Track tuples of (Subject Code, Raw Description)
        # ---------------------------------------------------------
        unmapped_course_codes: set[tuple[str, str]] = set()
        persisted_pages: list[ScrapePageRead] = []

        for page in pages:
            if not page.blob_key:
                skipped_pages += 1
                continue

            raw_bytes = blob_data_map.get(page.blob_key)
            if not raw_bytes:
                skipped_pages += 1
                continue

            pages_with_blob += 1
            html_text = raw_bytes.decode("utf-8", errors="ignore")

            page_text, title, external_links = parse_page_content(html_text, page.url)
            department_contact = parse_department_contact(html_text, page.url, external_links)
            additional = parse_additional_course_information(html_text, page.url, external_links)

            # Extract the RAW text first to use for logging
            raw_faculty, raw_departments, _ = parse_breadcrumbs(html_text)

            # Then resolve them for the database
            faculty = self.lexicon_resolver.resolve_faculty(raw_faculty)
            departments = [self.lexicon_resolver.resolve_subject(d) or "" for d in raw_departments]

            record_type = classify_calendar_url(page.url, faculty, departments, self.lexicon_profile)

            if not title.strip() or not page_text.strip():
                logger.warning(
                    "academic_calendar_empty_page_skipped",
                    url=page.url,
                    record_type=record_type.value,
                    empty_title=not title.strip(),
                    empty_content=not page_text.strip(),
                )
                skipped_pages += 1
                continue

            if record_type == AcademicCalendarType.COURSE:
                course_header = parse_course_header(html_text)
                if not course_header:
                    logger.warning("academic_calendar_course_header_unparsed", url=page.url)
                    skipped_pages += 1
                    continue

                subject_code, course_number, parsed_title, credit_json = course_header

                canonical_subject = self.lexicon_resolver.resolve_subject(subject_code)
                if not canonical_subject:
                    # Capture the raw description from the breadcrumb if available
                    raw_desc = raw_departments[-1] if raw_departments else "Unknown Description"
                    unmapped_course_codes.add((subject_code, raw_desc))
                    continue

                parsed_course_text = parse_course(html_text, page.url, external_links)

                if not parsed_course_text:
                    skipped_pages += 1
                    continue
                persisted_pages.append(page)
                all_course_payloads.append(
                    CourseCreate(
                        academic_year=academic_year,
                        campus="Waterloo",
                        institution="WLU",
                        subject=canonical_subject,
                        subject_code=subject_code,
                        course_number=course_number,
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

            persisted_pages.append(page)
            all_academic_records.append(
                WluPageCreate(
                    site_name=self.SITE_NAME,
                    version=academic_year,
                    url=page.url,
                    content_hash=page.content_hash,
                    record_type=record_type,
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

        async with self.school_db.start() as repos:
            if all_course_payloads:
                await repos.courses.upsert_courses(all_course_payloads)

            if all_academic_records:
                await repos.wlu_pages.upsert_wlu_pages(all_academic_records)

            if persisted_pages:
                await repos.scraping.update_scrape_pages(
                    page_ids=[page.id for page in persisted_pages],
                    update_data=ScrapePageUpdate(needs_persistence=False),
                )

        summary = {
            "pages_seen": len(pages),
            "pages_with_blob": pages_with_blob,
            "skipped_pages": skipped_pages,
            "course_payloads": len(all_course_payloads),
            "academic_records": len(all_academic_records),
        }

        logger.info("academic_calendar_batch_processed", **summary)
        return summary