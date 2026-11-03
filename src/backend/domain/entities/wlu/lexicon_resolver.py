"""WLU vocabulary: any name, alias or subject code (wlu_lexicon.yml) -> its canonical lexicon entry.

Shared by question extraction and by scraping (faculty names, registration headers), so it lives in
the domain beside the lexicon it reads. Pure lookups; maps are built once at startup.
"""
from collections.abc import Mapping

from backend.domain.entities.wlu.loris_registration import LexiconEntityType
from backend.domain.settings.profiles import LexiconEntry, WluLexicon


def lookup_key(value: str) -> str:
    return value.strip().casefold()


class WluLexiconResolver:
    """Case-insensitive lookup per lexicon section.

    "comp sci", "computer science" and "CP" all resolve to the Computer Science entry.
    """

    def __init__(self, lexicon_profile: WluLexicon):
        self.lexicon_profile = lexicon_profile
        # Departments double as subjects: each carries the course subject code ("CP").
        sections: dict[LexiconEntityType, Mapping[str, LexiconEntry]] = {
            LexiconEntityType.SUBJECT: lexicon_profile.departments,
            LexiconEntityType.DEPARTMENT: lexicon_profile.departments,
            LexiconEntityType.FACULTY: lexicon_profile.faculties,
            LexiconEntityType.REGISTRATION_NOTES: lexicon_profile.registration_notes,
        }
        self._sections = {entity_type: sections.get(entity_type, {}) for entity_type in LexiconEntityType}
        self._alias_maps: dict[LexiconEntityType, dict[str, LexiconEntry]] = {
            entity_type: self._alias_map(entries) for entity_type, entries in self._sections.items()
        }

    @staticmethod
    def _alias_map(entries: Mapping[str, LexiconEntry]) -> dict[str, LexiconEntry]:
        """{casefolded canonical name, alias or course code: entry} for one section."""
        aliases: dict[str, LexiconEntry] = {}
        for entry in entries.values():
            names = [entry.canonical, *entry.aliases]
            if entry.course_code:
                names.append(entry.course_code)
            for name in names:
                aliases[lookup_key(name)] = entry
        return aliases

    def get_aliases(self, entity_type: LexiconEntityType) -> list[str]:
        return list(self._alias_maps[entity_type])

    def course_codes(self, entity_type: LexiconEntityType) -> frozenset[str]:
        """The section's subject codes, casefolded like aliases ("it" for Italian's IT)."""
        return frozenset(
            lookup_key(entry.course_code)
            for entry in self._sections[entity_type].values() if entry.course_code
        )

    def get_entry(self, entity_type: LexiconEntityType, raw_value: str | None) -> LexiconEntry | None:
        if not raw_value:
            return None
        return self._alias_maps[entity_type].get(lookup_key(raw_value))

    def resolve(self, entity_type: LexiconEntityType, raw_value: str | None) -> str | None:
        entry = self.get_entry(entity_type, raw_value)
        return entry.canonical if entry else None

    def resolve_subject(self, raw_subject: str | None) -> str | None:
        return self.resolve(LexiconEntityType.SUBJECT, raw_subject)

    def resolve_course_code(self, raw_subject: str | None) -> str | None:
        entry = self.get_entry(LexiconEntityType.SUBJECT, raw_subject)
        return entry.course_code if entry else None

    def resolve_faculty(self, raw_faculty: str | None) -> str | None:
        return self.resolve(LexiconEntityType.FACULTY, raw_faculty)

    def department_name(self, raw_department: str) -> str:
        """The lexicon's canonical department name ("Arabic (Lang/Lit)" -> "Arabic"), or the name as
        given when the lexicon does not list it (calendar departments change more often than the lexicon)."""
        return self.resolve(LexiconEntityType.DEPARTMENT, raw_department) or raw_department

    def resolve_registration_header(self, header: str) -> str | None:
        return self.resolve(LexiconEntityType.REGISTRATION_NOTES, header)
