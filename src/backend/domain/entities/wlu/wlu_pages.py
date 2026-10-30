"""WLU pages: Academic Calendar programs/faculties/glossary and university website pages."""
import re
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

# Academic Calendar cross-listings whose whole body points elsewhere, e.g. "Program description link
# in Computer Science section." or "Refer to the Co-operative Education section." The body must START
# with the reference, so short real entries that merely end with "Refer to ..." are kept.
_REFERENCE_OPENING = re.compile(
    r"^\W*(?:please\s+)?(?:program\s+)?(?:description\s+link\s+in|refer\s+to|link\s+to|see)\b", re.IGNORECASE,
)
# Longer than this, the body has its own content even if it opens with a reference.
_REFERENCE_MAX_WORDS = 25
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


class FrozenSchool(BaseModel):
    model_config = ConfigDict(frozen=True)

class AcademicCalendarType(StrEnum):
    FACULTY = "faculty"
    DEPARTMENT = "department"
    PROGRAM = "program"
    PAGE = "page"
    COURSE = "course"
    GLOSSARY = "glossary"


class WluPageField(StrEnum):
    ID = "id"
    URL = "url"
    VERSION = "version"
    SITE_NAME = "site_name"
    RECORD_TYPE = "record_type"
    TITLE = "title"
    CONTENT = "content"
    METADATA_JSON = "metadata_json"
    CONTENT_HASH = "content_hash"
    NEEDS_EMBEDDING = "needs_embedding"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class WluPageMetadata(FrozenSchool):
    model_config = ConfigDict(extra="allow")

    department_contact: str | None = None
    external_links: list[str] | None = None

class WluPageBase(FrozenSchool):
    IDENTITY_FIELDS: ClassVar[tuple[WluPageField, ...]] = (
        WluPageField.VERSION,
        WluPageField.URL,
    )
    EMBED_FIELDS: ClassVar[tuple[WluPageField, ...]] = (
        WluPageField.SITE_NAME,
        WluPageField.RECORD_TYPE,
        WluPageField.TITLE,
        WluPageField.CONTENT,
    )

    site_name: str
    version: str
    url: str
    content_hash: str | None = None
    record_type: AcademicCalendarType
    title: str
    content: str
    needs_embedding: bool = True
    metadata_json: WluPageMetadata

    @property
    def is_reference_only(self) -> bool:
        """True when the page only points to another entry and has no content of its own."""
        # The body may repeat the title, sometimes as a link ("[Title](@@1@@): See ..."), before the reference.
        # Whitespace is normalized because scraped text mixes non-breaking and repeated spaces.
        body = " ".join(_MARKDOWN_LINK.sub(r"\1", self.content).split())
        title = " ".join(self.title.split())
        while title and body.startswith(title):
            body = body[len(title):].lstrip(" :.-")
        return bool(_REFERENCE_OPENING.match(body)) and len(body.split()) <= _REFERENCE_MAX_WORDS

class WluPageCreate(WluPageBase):
    pass

class WluPageUpdate(FrozenSchool):
    """Strictly typed payload for partial updates."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    content: str | None = None
    content_hash: str | None = None
    needs_embedding: bool | None = None
    site_name: str | None = None
    record_type: AcademicCalendarType | None = None

class WluPageRead(WluPageBase):
    id: int


