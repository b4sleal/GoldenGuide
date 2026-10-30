"""Paging and sort options for the school repositories."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from backend.domain.entities.scraping import ScrapePageField
from backend.domain.entities.wlu.course import CourseField
from backend.domain.entities.wlu.loris_registration import CourseTermField
from backend.domain.entities.wlu.wlu_pages import WluPageField
from backend.domain.ports.repositories.pagination import PageParams
from backend.domain.ports.repositories.sorting import SortSpec


# Strict whitelist to prevent sorting of dangerous/unsortable fields
# e.g. long descriptions, etc
class CourseSortField(StrEnum):
    ID = CourseField.ID
    SUBJECT = CourseField.SUBJECT
    SUBJECT_CODE = CourseField.SUBJECT_CODE
    COURSE_NUMBER = CourseField.COURSE_NUMBER
    TITLE = CourseField.TITLE
    ACADEMIC_YEAR = CourseField.ACADEMIC_YEAR

class CourseTermSortField(StrEnum):
    ID = CourseTermField.ID
    TERM_CODE = CourseTermField.TERM_CODE
    CRN = CourseTermField.CRN
    SECTION_CODE = CourseTermField.SECTION_CODE

class WluPageSortField(StrEnum):
    ID = WluPageField.ID
    SITE_NAME = WluPageField.SITE_NAME
    RECORD_TYPE = WluPageField.RECORD_TYPE
    TITLE = WluPageField.TITLE
    URL = WluPageField.URL

class ScrapePageSortField(StrEnum):
    ID = ScrapePageField.ID
    STATUS = ScrapePageField.STATUS
    LAST_ATTEMPTED_AT = ScrapePageField.LAST_ATTEMPTED_AT
    LAST_SUCCESS_AT = ScrapePageField.LAST_SUCCESS_AT
    URL = ScrapePageField.URL

# Params for each repository query type, with the appropriate order enum specified.
class CoursePageParams(PageParams[CourseSortField]):
    order_by: list[SortSpec[CourseSortField]] = Field(default_factory=list)

class CourseTermParams(PageParams[CourseTermSortField]):
    order_by: list[SortSpec[CourseTermSortField]] = Field(default_factory=list)

class WluPageParams(PageParams[WluPageSortField]):
    order_by: list[SortSpec[WluPageSortField]] = Field(default_factory=list)

class ScrapePageParams(PageParams[ScrapePageSortField]):
    order_by: list[SortSpec[ScrapePageSortField]] = Field(default_factory=list)

