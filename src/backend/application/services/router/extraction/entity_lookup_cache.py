"""The EntityLookup the extractor matches questions against, cached because it is a whole-catalog scan.

The cache is optional: if it is unreachable, the lookup comes from the last copy this process loaded,
or from Postgres, so a cache outage slows questions down instead of failing them.
"""
import asyncio

import structlog
from pydantic import ValidationError

from backend.domain.entities.question import EntityLookup
from backend.domain.entities.wlu.loris_registration import CourseFaculty
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.ports.providers.caching.cache import Cache
from backend.domain.ports.repositories.filters import CourseFilter, WluPageFilter
from backend.domain.ports.repositories.school.query_types import (
    CoursePageParams,
    WluPageParams,
)
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.institution import InstitutionProfile
from backend.domain.settings.router import EntityLookupCacheSettings

logger = structlog.get_logger(__name__)


class EntityLookupCache:
    """Loads the EntityLookup (known courses, subjects, programs, rooms, instructors) and caches it."""

    # Bump whenever the EntityLookup payload shape changes, so stale entries are never read. A code
    # fact, not configuration: it must change together with the model.
    PAYLOAD_VERSION = 5

    def __init__(
            self,
            school_db: SchoolDB,
            cache: Cache,
            institution: InstitutionProfile,
            settings: EntityLookupCacheSettings,
    ):
        self.school_db = school_db
        self.cache = cache
        self.institution = institution.code
        self.cache_key = f"{institution.code.casefold()}:entity_lookup_lists:v{self.PAYLOAD_VERSION}"
        self.ttl = settings.ttl_seconds
        self.batch_size = settings.batch_size
        # Single flight per process: when the entry expires, concurrent questions wait for one reload
        # instead of each scanning the catalog. Instances still reload independently (at most one each).
        self._refresh_lock = asyncio.Lock()
        # The last lookup this process loaded: served while the cache is unreachable, so an outage
        # does not turn every question into a full catalog scan.
        self._last_loaded: EntityLookup | None = None

    async def get_lookup_data(self) -> EntityLookup:
        if (cached := await self.read_cached()) is not None:
            return cached

        async with self._refresh_lock:
            # Another task may have reloaded while this one waited.
            if (cached := await self.read_cached()) is not None:
                return cached
            return await self.refresh_cache()

    async def read_cached(self) -> EntityLookup | None:
        """The cached lookup; None on a miss or an invalid entry. A cache outage falls back to the last loaded copy."""
        try:
            cached = await self.cache.get(self.cache_key)
        except Exception as exc:
            logger.warning("entity_cache_unavailable", key=self.cache_key, error_type=type(exc).__name__, error=str(exc))
            return self._last_loaded
        if not cached:
            return None
        try:
            return EntityLookup.model_validate_json(cached)
        except ValidationError:
            logger.warning("entity_cache_invalid", key=self.cache_key)
            return None

    async def refresh_cache(self) -> EntityLookup:
        """Reload the lookup from Postgres and cache it. Database errors propagate: there is no other source."""
        logger.info("entity_cache_refresh_started")

        courses = set()
        subjects = {}
        programs = set()

        async with self.school_db.start() as repos:
            # Every course of the institution, paged so no single query loads the whole catalog.
            offset = 0

            while True:
                batch = await repos.courses.fetch_courses(
                    page_params=CoursePageParams(
                        limit=self.batch_size,
                        offset=offset,
                    ),
                    filters=CourseFilter(institution=self.institution),
                )

                for course in batch:
                    code = f"{course.subject_code}{course.course_number}"
                    courses.add(code)

                    if course.subject and course.subject_code:
                        subjects[course.subject] = course.subject_code

                if len(batch) < self.batch_size:
                    break

                offset += len(batch)

            # Load program names from academic calendar records.
            offset = 0

            while True:
                batch = await repos.wlu_pages.fetch_records(
                    page_params=WluPageParams(
                        limit=self.batch_size,
                        offset=offset,
                    ),
                    filters=WluPageFilter(
                        record_type=AcademicCalendarType.PROGRAM,
                    ),
                )

                for page in batch:
                    if page.title:
                        programs.add(page.title)

                if len(batch) < self.batch_size:
                    break

                offset += len(batch)

            # Distinct meeting rooms (~170): small enough to hold whole, like courses.
            rooms = await repos.course_terms.fetch_meeting_rooms()
            instructors = await repos.course_terms.fetch_instructors()

        data = EntityLookup(
            courses=sorted(courses),
            subjects=dict(sorted(subjects.items())),
            programs=sorted(programs),
            rooms=rooms,
            # Identity and name only: no contact details in the shared cache.
            instructors=[
                CourseFaculty(bannerId=instructor.bannerId, displayName=instructor.displayName)
                for instructor in instructors
            ],
        )

        self._last_loaded = data

        # Cache only after every repository query succeeds. A failed write only costs a reload later.
        try:
            await self.cache.set(
                self.cache_key,
                data.model_dump_json(exclude_none=True).encode("utf-8"),
                ttl=self.ttl,
            )
        except Exception as exc:
            logger.warning("entity_cache_write_failed", key=self.cache_key, error_type=type(exc).__name__, error=str(exc))

        logger.info(
            "entity_cache_refresh_completed",
            courses=len(courses),
            subjects=len(subjects),
            programs=len(programs),
            rooms=len(rooms),
            instructors=len(instructors),
        )

        return data