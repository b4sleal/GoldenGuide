"""Shared router fixtures: the real WLU lexicon, an entity lookup shaped like production data, and the
production extractor built from them."""
from pathlib import Path

import pytest
import yaml

from backend.application.services.router.extraction.entity_extractor import (
    PreLLMExtractor,
)
from backend.application.services.router.extraction.matchers.course_matcher import (
    CourseCodeMatcher,
)
from backend.application.services.router.extraction.matchers.department_hint_matcher import (
    DepartmentHintMatcher,
)
from backend.application.services.router.extraction.matchers.instructor_matcher import (
    InstructorMatcher,
)
from backend.application.services.router.extraction.matchers.lexicon_matcher import (
    LexiconEntityMatcher,
)
from backend.application.services.router.extraction.matchers.room_matcher import (
    RoomMatcher,
)
from backend.domain.entities.question import EntityLookup
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.loris_registration import CourseFaculty, MeetingRoom
from backend.domain.settings.profiles import WluLexicon

CONFIG_DIR = Path(__file__).parents[6] / "configs" / "catalogs" / "text_enrichment"
LEXICON_FILE = CONFIG_DIR / "wlu_lexicon.yml"


def load_catalog(path: Path, section: str) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["catalog"]["text_enrichment"][section]


@pytest.fixture(scope="session")
def lexicon_resolver() -> WluLexiconResolver:
    """The production lexicon, so tests prove "computer science" really resolves to CP."""
    return WluLexiconResolver(WluLexicon.model_validate(load_catalog(LEXICON_FILE, "wlu_lexicon")))


@pytest.fixture
def lookup() -> EntityLookup:
    """EntityLookupCache payload. Rooms mirror real LORIS shapes:
    prefixed (LH/LH1009), unprefixed (SC/N3021, ART/1C17), a name shared by two buildings
    (GYM), and a room that is also a course code (BAB/BA101)."""
    return EntityLookup(
        courses=["BA101", "CP104", "CP213", "CP220", "CP317", "MA103"],
        subjects={"Computer Science": "CP", "Mathematics": "MA"},
        rooms=[
            MeetingRoom(building=building, room=name)
            for building, name in [
                ("AC", "GYM"), ("ART", "1C17"), ("BAB", "BA101"), ("LH", "LH1009"),
                ("LH", "LH3060"), ("SC", "N3021"), ("US", "GYM"),
            ]
        ],
        instructors=[
            CourseFaculty(bannerId="100", displayName="Heider Ali"),
            CourseFaculty(bannerId="101", displayName="Ali Hosseini"),
            CourseFaculty(bannerId="102", displayName="Alison Blay-Palmer"),
        ],
    )


class StaticEntityCache:
    def __init__(self, data: EntityLookup):
        self.data = data

    async def get_lookup_data(self) -> EntityLookup:
        return self.data


@pytest.fixture
def extractor(lexicon_resolver, lookup) -> PreLLMExtractor:
    """The production matcher chain, in production order (core/di/wiring/router.py)."""
    return PreLLMExtractor(
        StaticEntityCache(lookup),
        [
            CourseCodeMatcher(lexicon_resolver),
            RoomMatcher(),
            InstructorMatcher(),
            LexiconEntityMatcher(lexicon_resolver),
            DepartmentHintMatcher(lexicon_resolver),
        ],
    )
