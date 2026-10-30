"""What GoldenGuide understands of a student's question, before any retrieval.

    question --extraction--> MaskedQuestion (text with "[COURSE1]" masks + one entity per mask)
"""
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.entities.wlu.loris_registration import CourseFaculty, MeetingRoom


class EntityType(StrEnum):
    """Kinds of things recognized in a question. The upper-case value is its mask prefix ("[COURSE1]")."""
    COURSE = "course"
    SUBJECT = "subject"
    DEPARTMENT = "department"
    FACULTY = "faculty"
    PROGRAM = "program"
    ROOM = "room"
    INSTRUCTOR = "instructor"


# Disciplines that carry a course subject code ("CP"), so courses, sections and program titles can be
# filtered by them. The lexicon tags "computer science" as a department, so both kinds count.
SUBJECT_TYPES = frozenset({EntityType.SUBJECT, EntityType.DEPARTMENT})


class EntityMatch(StrEnum):
    EXACT = "exact"
    FUZZY_HINT = "fuzzy_hint"  # A spelling guess ("psycho" -> Psychology): only the LLM may use it.


class FrozenQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)


class CourseEntity(FrozenQuestion):
    type: Literal[EntityType.COURSE] = EntityType.COURSE
    raw: str
    normalized: str = Field(description="Catalog code, e.g. CP220.")


class DisciplineEntity(FrozenQuestion):
    """A faculty, department or subject, from the WLU lexicon or the course catalog."""
    type: Literal[EntityType.FACULTY, EntityType.DEPARTMENT, EntityType.SUBJECT]
    raw: str | None = None
    canonical: str
    code: str | None = Field(default=None, description="Course subject code, e.g. CP.")
    match: EntityMatch = EntityMatch.EXACT
    derived_from: str | None = Field(default=None, description="Mask of the course this subject was derived from.")


class ProgramEntity(FrozenQuestion):
    type: Literal[EntityType.PROGRAM] = EntityType.PROGRAM
    canonical: str
    record_id: int


class RoomEntity(FrozenQuestion):
    type: Literal[EntityType.ROOM] = EntityType.ROOM
    raw: str
    canonical: str
    rooms: list[MeetingRoom]


class InstructorEntity(FrozenQuestion):
    type: Literal[EntityType.INSTRUCTOR] = EntityType.INSTRUCTOR
    raw: str
    canonical: str
    instructors: list[CourseFaculty]


ExtractedEntity = Annotated[
    CourseEntity | DisciplineEntity | ProgramEntity | RoomEntity | InstructorEntity,
    Field(discriminator="type"),
]

EntityMap = dict[str, ExtractedEntity]  # Mask ("[COURSE1]") -> entity.


class MaskedQuestion(FrozenQuestion):
    text: str
    entities: EntityMap = Field(default_factory=dict)


class EntityLookup(FrozenQuestion):
    """Reference data entity extraction matches against, loaded from the school database and cached."""
    courses: list[str] = Field(default_factory=list, description="Catalog codes, e.g. CP220.")
    subjects: dict[str, str] = Field(default_factory=dict, description="Subject name -> subject code.")
    programs: list[str] = Field(default_factory=list)
    rooms: list[MeetingRoom] = Field(default_factory=list)
    instructors: list[CourseFaculty] = Field(default_factory=list)
