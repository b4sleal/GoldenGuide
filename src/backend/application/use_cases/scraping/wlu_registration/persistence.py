"""Turn one term's LORIS extraction (blob) into course and course-term rows.

Order matters: unknown subject codes stop the import before anything is written (add them to
wlu_lexicon.yml); courses missing from the catalog are inserted (insert-only, never overwriting
Academic Calendar data); then each section is linked to its course of the governing academic year
and upserted. Sections whose course cannot be resolved are counted (unmapped_ghost_courses), not stored.
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from backend.application.use_cases.scraping.common_parsing import clean_text_value, clean_html_to_markdown
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.application.use_cases.scraping.wlu_registration.parse import (
    build_course_payload, term_code_to_academic_year, build_course_term_payload, parse_registration_description,
    parse_requirement_table, has_meeting_faculty
)
from backend.application.use_cases.scraping.wlu_registration.scrape import loris_term_blob_key
from backend.domain.entities.wlu.course import CourseCreate, CourseLookupRead
from backend.domain.entities.wlu.loris_registration import CourseTermCreate
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.filters import CourseFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.ports.repositories.school.query_types import CoursePageParams

logger = structlog.get_logger()

# LORIS placeholder text that carries no information (and would only cost embedding/prompt space).
LORIS_BOILERPLATE = [
    r"(?i)^display course description\s*\n?",
    r"(?i)^if there is a section description, display the new label and the description when there is no course or section description, provide the no information message\s*\n*"
]


class WLURegistrationPersistence:
    def __init__(self, school_db: SchoolDB, blob_storage: BlobStorage, lexicon_resolver: WluLexiconResolver):
        self.school_db = school_db
        self.blob_storage = blob_storage
        self.lexicon_resolver = lexicon_resolver

    async def ingest_from_blob(self, term_code: str) -> dict[str, Any]:
        blob_key = loris_term_blob_key(term_code)

        try:
            json_bytes = await self.blob_storage.download(blob_key)
        except Exception as exc:
            # Usually a missing extraction, but keep the cause: a storage outage looks the same otherwise.
            raise ValueError(
                f"Could not read the extraction for term '{term_code}' ({blob_key}). "
                f"Run extraction first if it does not exist."
            ) from exc

        raw_data = json.loads(json_bytes.decode("utf-8"))

        # Gatekeeper: every subject code must be in the lexicon before anything is written.
        unmapped_codes: set[tuple[str, str]] = set()

        for item in raw_data:
            subject_code = clean_text_value(item["section"].get("subject"))
            subject_desc = clean_text_value(item["section"].get("subjectDescription")) or "Unknown Description"

            if subject_code and not self.lexicon_resolver.resolve_subject(subject_code):
                unmapped_codes.add((subject_code, subject_desc))

        if unmapped_codes:
            unmapped_list = [f"[{code}] '{desc}'" for code, desc in unmapped_codes]
            raise ValueError(
                f"Strict Gatekeeper Block: Unmapped LORIS subject codes found: {unmapped_list}. "
                f"Please add them to wlu_lexicon.yml and retry the ingestion batch."
            )

        raw_course_fragments: list[CourseCreate] = []
        pending_term_fragments: list[dict[str, Any]] = []

        for item in raw_data:
            section = item["section"]

            subject_code = clean_text_value(section.get("subject"))
            canonical_subject = self.lexicon_resolver.resolve_subject(subject_code) or ""

            restrictions_text = clean_html_to_markdown(
                item.get("restrictions_html")
            )

            description_text = clean_html_to_markdown(
                item.get("description_html")
            )

            if description_text:
                for pattern in LORIS_BOILERPLATE:
                    description_text = re.sub(
                        pattern, "", description_text
                    ).strip()

            menu_prereq = parse_requirement_table(
                item.get("prereq_html"),
                self.lexicon_resolver,
            )

            menu_coreq = parse_requirement_table(
                item.get("coreq_html"),
                self.lexicon_resolver,
            )

            description = parse_registration_description(
                description_text,
                self.lexicon_resolver,
                menu_prereq=menu_prereq,
                menu_coreq=menu_coreq,
            )

            course_fragment = build_course_payload(
                section,
                term_code,
                canonical_subject,
            )

            raw_course_fragments.append(course_fragment)

            pending_term_fragments.append({
                "subject_code": subject_code,
                "course_number": course_fragment.course_number,
                "institution": course_fragment.institution,
                "canonical_subject": canonical_subject,
                "section": section,
                "restrictions_text": restrictions_text,
                "description": description,
            })

        governing_year = term_code_to_academic_year(term_code)
        lookup_keys = set((p["subject_code"], p["course_number"], p["institution"]) for p in pending_term_fragments)

        if not lookup_keys:
            return {"term_code": term_code, "processed_sections": 0, "course_terms_upserted": 0}
        inserted = 0

        async with self.school_db.start() as repos:
            inserted = await repos.courses.insert_courses(raw_course_fragments)

            calendar_candidates = await repos.courses.fetch_courses(
                page_params=CoursePageParams(limit=max(1, len(lookup_keys) * 5)),
                filters=CourseFilter(
                    academic_year=governing_year,
                    specific_course_codes=lookup_keys,
                ),
                view_model=CourseLookupRead,
            )

        candidate_map = {
            (c.subject_code, c.course_number, c.institution): c.id
            for c in calendar_candidates
        }

        final_term_payloads: list[CourseTermCreate] = []
        meeting_level_faculty = 0
        unmapped_count = 0

        for pending in pending_term_fragments:
            key = (
                pending["subject_code"],
                pending["course_number"],
                pending["institution"],
            )

            resolved_course_id = candidate_map.get(key)

            if resolved_course_id is None:
                unmapped_count += 1
                continue

            term_payload = build_course_term_payload(
                section=pending["section"],
                course_id=resolved_course_id,
                term_code=term_code,
                description=pending["description"],
                restrictions_text=pending["restrictions_text"],
                canonical_subject=pending["canonical_subject"],
            )

            final_term_payloads.append(term_payload)
            meeting_level_faculty += has_meeting_faculty(pending["section"])

        # Data-shape check: makes a LORIS format change visible in logs instead of silently
        # producing empty columns (as happened when instructors were read from the wrong list).
        #   instructor_tba        sections with no instructor yet (normal: Banner shows "TBA")
        #   meeting_level_faculty sections where LORIS filled per-meeting instructors (0 in class search)
        logger.info(
            "loris_faculty_summary",
            term_code=term_code,
            sections=len(final_term_payloads),
            instructor_tba=sum(not payload.faculty for payload in final_term_payloads),
            meeting_level_faculty=meeting_level_faculty,
        )

        async with self.school_db.start() as repos:
            if final_term_payloads:
                await repos.course_terms.upsert_course_terms(final_term_payloads)

        return {
            "term_code": term_code,
            "processed_sections": len(pending_term_fragments),
            "inserted_courses": inserted,
            "course_terms_upserted": len(final_term_payloads),
            "unmapped_ghost_courses": unmapped_count,
        }