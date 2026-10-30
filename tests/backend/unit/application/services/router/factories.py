"""Typed entity builders for router tests: the same domain objects the extractor produces, plus the
production institution and router settings (configs/catalogs), so tests never restate them."""
from pathlib import Path

import yaml

from backend.domain.entities.question import (
    CourseEntity,
    DisciplineEntity,
    EntityMatch,
    EntityType,
    InstructorEntity,
    ProgramEntity,
    RoomEntity,
)
from backend.domain.entities.wlu.loris_registration import CourseFaculty, MeetingRoom
from backend.domain.settings.institution import InstitutionProfile
from backend.domain.settings.router import RouterSettings

CATALOG_DIR = Path(__file__).parents[6] / "configs" / "catalogs"


def catalog_section(relative_path: str, section: str) -> dict:
    return yaml.safe_load((CATALOG_DIR / relative_path).read_text(encoding="utf-8"))["catalog"][section]


INSTITUTION = InstitutionProfile.model_validate(catalog_section("institution/institution.yml", "institution"))
ROUTER_SETTINGS = RouterSettings.model_validate(catalog_section("router/router.yml", "router"))


def course(code: str, raw: str | None = None) -> CourseEntity:
    return CourseEntity(raw=raw or code, normalized=code)


def department(canonical: str, code: str | None, *, fuzzy: bool = False) -> DisciplineEntity:
    return DisciplineEntity(
        type=EntityType.DEPARTMENT,
        raw=canonical.lower(),
        canonical=canonical,
        code=code,
        match=EntityMatch.FUZZY_HINT if fuzzy else EntityMatch.EXACT,
    )


def subject(canonical: str, code: str | None) -> DisciplineEntity:
    return DisciplineEntity(type=EntityType.SUBJECT, raw=canonical.lower(), canonical=canonical, code=code)


def faculty(canonical: str) -> DisciplineEntity:
    return DisciplineEntity(type=EntityType.FACULTY, raw=canonical.lower(), canonical=canonical)


def room(*rooms: tuple[str | None, str]) -> RoomEntity:
    meeting_rooms = [MeetingRoom(building=building, room=name) for building, name in rooms]
    return RoomEntity(raw=rooms[0][1], canonical=" / ".join(name for _, name in rooms), rooms=meeting_rooms)


def instructor(banner_id: str, name: str) -> InstructorEntity:
    return InstructorEntity(raw=name, canonical=name, instructors=[CourseFaculty(bannerId=banner_id, displayName=name)])


def program(title: str, record_id: int) -> ProgramEntity:
    return ProgramEntity(canonical=title, record_id=record_id)


CS = department("Computer Science", "CP")
PSYCH = department("Psychology", "PS")
LH1009 = room(("LH", "LH1009"))
HEIDER_ALI = instructor("100", "Heider Ali")
