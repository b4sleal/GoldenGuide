"""Resolve plan masks into the typed entities compilers need, rejecting anything else.

Every function raises ValueError for a mask that is unknown or of the wrong kind, so an invalid plan
fails loudly in compilation instead of silently querying without that restriction. ValueError, not
TypeError, on purpose: the orchestrator reports ValueError as an unsupported plan (a gap in the answer),
while any other exception is reported as a failed data source.
"""
import re

from pydantic import BaseModel

from backend.domain.entities.question import (
    SUBJECT_TYPES,
    CourseEntity,
    DisciplineEntity,
    EntityMap,
    EntityType,
    InstructorEntity,
    RoomEntity,
)
from backend.domain.entities.wlu.loris_registration import MeetingRoom

COURSE_CODE = re.compile(r"([A-Z]{2})(\d{3}[A-Z]?)")


def course_code(mask: str, entities: EntityMap) -> tuple[str, str]:
    """(subject code, course number) of a course mask: "[COURSE1]" -> ("CP", "220")."""
    entity = entities.get(mask)
    if not isinstance(entity, CourseEntity):
        raise ValueError(f"Invalid course entity: {mask}")  # noqa: TRY004 (see module docstring)
    match = COURSE_CODE.fullmatch(entity.normalized)
    if not match:
        raise ValueError(f"Invalid course code: {entity.normalized}")
    subject, number = match.groups()
    return subject, number


def subject_code(mask: str, entities: EntityMap) -> str:
    """Course subject code of a subject or department mask. Departments carry one too: the lexicon tags
    "computer science" as a department, and ignoring it used to return every course."""
    entity = entities.get(mask)
    if not isinstance(entity, DisciplineEntity) or entity.type not in SUBJECT_TYPES:
        raise ValueError(f"Invalid subject entity: {mask}")
    if not entity.code:
        raise ValueError(f"Unresolved subject: {mask}")
    return entity.code


def masks_of_type(masks: list[str], entities: EntityMap, *types: EntityType) -> list[str]:
    """The known masks among `masks` whose entity is one of `types` (unknown masks are checked by callers)."""
    return [mask for mask in masks if mask in entities and entities[mask].type in types]


def meeting_rooms(masks: list[str], entities: EntityMap) -> list[MeetingRoom]:
    """Every room the room masks stand for, de-duplicated in order."""
    rooms = []
    for mask in masks:
        entity = entities.get(mask)
        if not isinstance(entity, RoomEntity) or not entity.rooms:
            raise ValueError(f"Invalid room: {mask}")
        rooms.extend(entity.rooms)
    return list(dict.fromkeys(rooms))


def instructor_ids(masks: list[str], entities: EntityMap) -> list[str]:
    """LORIS banner ids of every instructor the masks stand for, de-duplicated in order."""
    ids = []
    for mask in masks:
        entity = entities.get(mask)
        if not isinstance(entity, InstructorEntity) or not entity.instructors:
            raise ValueError(f"Invalid instructor: {mask}")
        ids.extend(instructor.bannerId for instructor in entity.instructors if instructor.bannerId)
    return list(dict.fromkeys(ids))


def unsupported_fields(given: BaseModel, supported: BaseModel) -> list[str]:
    """Fields set in `given` that its `supported` projection (a copy holding only what a compiler can
    execute) dropped. Compilers raise NotImplementedError for these rather than ignore them."""
    return sorted(set(given.model_dump(exclude_none=True)) - set(supported.model_dump(exclude_none=True)))
