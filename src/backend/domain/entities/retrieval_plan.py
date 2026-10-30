"""The retrieval plan: what to fetch for a question. Produced by the deterministic planner or the LLM router.

Pure data. Parsing leniency for LLM output lives at the LLM boundary
(application/services/router/planning/llm/response_model.py); operation rules live in
application/services/router/planning/llm/plan_validation.py.
"""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from backend.domain.entities.wlu.academic_calendar import Season, Weekday

CampusType = Literal["waterloo", "brantford", "milton", "online"]
DeliveryType = Literal["online", "in_person", "hybrid"]
SubTermType = Literal["6_week", "12_week"]


class RetrievalSource(StrEnum):
    COURSES = "courses"
    COURSE_TERMS = "course_terms"
    WLU_PAGES = "wlu_pages"
    VECTOR = "vector"


class RetrievalOperation(StrEnum):
    LOOKUP = "lookup"
    FILTER = "filter"
    RELATED = "related"
    SEMANTIC = "semantic"


class CourseRelationship(StrEnum):
    PREREQUISITE_OF = "prerequisite_of"
    COREQUISITE_OF = "corequisite_of"
    EXCLUDES = "excludes"


class EvidenceRole(StrEnum):
    REQUIRED = "required"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"


class EntityOperator(StrEnum):
    """How several entities of one request combine: "computer science AND psychology" programs."""
    ALL = "all"
    ANY = "any"


class TermYearCombo(BaseModel):
    term: Season
    year: int | None = Field(
        default=None,
        ge=1000,
        le=9999,
        description=(
            "The calendar year of this term, only if the student stated or clearly implied one. "
            "Leave empty for a bare season like 'winter'; it resolves to the next occurrence."
        ),
    )


class CourseSpecificFilters(BaseModel):
    include: bool | None = Field(
        default=None,
        description="True to include/search for this course; false to exclude or avoid it.",
    )
    admin_action: Literal[
        "petition", "grade_appeal", "exam_deferral", "drop", "add", "waitlist", "swap",
    ] | None = None
    grade: str | None = None
    credit: float | None = None
    campus: CampusType | None = None
    delivery: DeliveryType | None = None
    sub_term: SubTermType | None = None
    target_terms: list[TermYearCombo] | None = Field(
        default=None,
        description="Explicit term/year pairings for an individual course.",
    )
    lab: bool | None = None
    tutorial: bool | None = None
    seminar: bool | None = None


class EntityLogic(BaseModel):
    include: bool = Field(description="True to include this entity; false to exclude it.")


class GlobalFilters(BaseModel):
    """Database search restrictions, not conversational student context."""

    subjects: list[str] | None = Field(default=None, description="Masked subjects used as search restrictions.")
    exact_course_number: list[str] | None = Field(
        default=None, description="Course numbers without a subject, not year levels.",
    )
    credit: list[float] | None = None
    campus: list[CampusType] | None = None
    delivery: list[DeliveryType] | None = None
    term: list[Season] | None = None
    sub_term: list[SubTermType] | None = None
    year: list[int] | None = None
    lab: bool | None = None
    tutorial: bool | None = None
    seminar: bool | None = None
    level: list[int] | None = None
    day_preference: list[Weekday] | None = None
    day_exclusion: list[Weekday] | None = None
    rooms: list[str] | None = Field(
        default=None, description="Masked rooms ([ROOM1]) restricting where a section meets.",
    )
    instructors: list[str] | None = Field(
        default=None, description="Masked instructors ([INSTRUCTOR1]) restricting who teaches a section.",
    )
    schedule_time_masks: list[str] | None = Field(
        default=None, description="Masked times explicitly restricting a schedule search.",
    )


class ConversationContext(BaseModel):
    """Student context for reasoning, never database filtering."""

    student_type: Literal["domestic", "international"] | None = None
    load_status: Literal["full_time", "part_time"] | None = None
    coop_status: bool | None = None
    academic_standing: Literal["probation", "good_standing"] | None = None
    completed_courses: list[str] | None = Field(
        default=None, description="Masked courses the student states they completed.",
    )
    historical_grades: list[str] | None = None
    reference_time_masks: list[str] | None = Field(
        default=None, description="Times concerning deadlines or context, not schedules.",
    )


class RetrievalRequest(BaseModel):
    source: RetrievalSource
    operation: RetrievalOperation
    entities: list[str] = Field(default_factory=list)
    relationship: CourseRelationship | None = None
    entity_operator: EntityOperator = EntityOperator.ALL
    role: EvidenceRole = EvidenceRole.REQUIRED
    requested_fields: list[
        Literal["description", "prereq", "coreq", "exclusions", "notes", "credit_json", "schedule", "availability"]
    ] = Field(default_factory=list)
    filters: GlobalFilters | None = Field(default=None, description="Restrictions applicable only to this request.")


class RetrievalPlan(BaseModel):
    requests: list[RetrievalRequest] = Field(default_factory=list)
    semantic_fallback: bool = True


class PreLLMExtraction(BaseModel):
    course_specific_filters: dict[str, CourseSpecificFilters] = Field(default_factory=dict)
    extracted_entities_logic: dict[str, EntityLogic] = Field(default_factory=dict)
    global_filters: GlobalFilters = Field(default_factory=GlobalFilters)
    conversation_context: ConversationContext = Field(default_factory=ConversationContext)
    retrieval: RetrievalPlan = Field(default_factory=RetrievalPlan)
