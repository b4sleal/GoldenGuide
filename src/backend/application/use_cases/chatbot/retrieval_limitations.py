"""Tell the answer model which parts of a question could not be answered from WLU data.

Without this, a retrieval that failed or found nothing disappears silently: the model sees only
whatever other evidence was retrieved and may answer with it. For example, a failed "CP220 in winter"
lookup let the model answer from Fall records. This module turns retrieval outcomes into short,
plain-language notes appended to the context, so the model can say exactly what is missing.

Rules:
    - Requests the student's question planned (router output) are always reported when they
      failed, were unsupported, or found no records: that is a part of the question left unanswered.
    - Requests the orchestrator added automatically (e.g. a course-details lookup for every course
      mentioned) are reported only when a system FAILED. An extra lookup that found nothing is not
      a gap in the student's question; an outage might be.
    - Planned requests whose results were cut off by a limit are reported as "Search limited to N
      results", so the answer never presents a partial list as complete.
    - Notes describe WHAT was not checked, never WHY technically: exception text stays in the logs.

Pure functions, no I/O: easy to unit test.
"""
from backend.domain.entities.question import CourseEntity, EntityMap
from backend.domain.entities.retrieval import RetrievalOutcome, RetrievalStatus
from backend.domain.entities.retrieval_plan import RetrievalRequest, RetrievalSource

# What each source contains, in the words the answer model should use.
_SOURCE_LABELS = {
    RetrievalSource.COURSES: "Academic Calendar course details",
    RetrievalSource.COURSE_TERMS: "LORIS course offerings (term sections)",
    RetrievalSource.WLU_PAGES: "WLU program and information pages",
    RetrievalSource.VECTOR: "WLU documents",
}

# Heading the generation prompt refers to (configs/base/ai_behavior.yml, rule 3).
SECTION_HEADING = "RETRIEVAL LIMITATIONS (not citable sources)"


def describe_request(request: RetrievalRequest, entities: EntityMap) -> str:
    """One-line description of what a request looked for, e.g.
    'LORIS course offerings (term sections) for CP220 (term: winter)'."""
    # Step 1: which records.
    parts = [_SOURCE_LABELS.get(request.source, request.source.value)]

    # Step 2: about what. Masks like [COURSE1] are replaced by the name the student would recognise.
    names = [_entity_name(mask, entities) for mask in request.entities]
    if names:
        parts.append("for " + ", ".join(names))

    # Step 3: with which restrictions (only the ones that change the meaning of "not found").
    filters = request.filters
    if filters:
        qualifiers = []
        if filters.term:
            qualifiers.append("term: " + ", ".join(filters.term))
        if filters.year:
            qualifiers.append("year: " + ", ".join(str(year) for year in filters.year))
        if filters.level:
            qualifiers.append("level: " + ", ".join(str(level) for level in filters.level))
        if qualifiers:
            parts.append(f"({'; '.join(qualifiers)})")

    return " ".join(parts)


def limitation_notes(
        outcomes: list[RetrievalOutcome],
        planned_keys: set[str],
        request_key,
        entities: EntityMap,
) -> list[str]:
    """Notes for the answer model, one per gap, in outcome order.

    `planned_keys` identifies the requests that came from the student's question (see module rules);
    `request_key` is the same function the orchestrator uses to de-duplicate requests.
    """
    notes: list[str] = []

    for outcome in outcomes:
        planned = request_key(outcome.request) in planned_keys
        what = describe_request(outcome.request, entities)

        if outcome.status == RetrievalStatus.FAILED:
            # Always reported: a system outage can make any answer incomplete.
            notes.append(f"Could not check {what}: the data source was temporarily unavailable.")

        elif not planned:
            # Automatic extras that were unsupported or empty are not gaps in the question.
            continue

        elif outcome.status == RetrievalStatus.UNSUPPORTED:
            notes.append(f"Could not check {what}: this kind of search is not supported yet.")

        elif outcome.count == 0:
            notes.append(f"Checked {what}: no matching records were found.")

        elif outcome.truncated_at:
            notes.append(
                f"Search limited to {outcome.truncated_at} results for {what}: more matching records exist."
            )

    # The same gap can be produced twice (e.g. identical descriptions); keep each once, in order.
    return list(dict.fromkeys(notes))


def semantic_failure_note() -> str:
    """Semantic search failed on every profile, so only structured records were checked."""
    return f"Could not check {_SOURCE_LABELS[RetrievalSource.VECTOR]}: the data source was temporarily unavailable."


def context_limit_note(shown: int, total: int) -> str:
    """The prompt holds at most `shown` structured records; any tables still list every record."""
    return f"Search limited to {shown} results: {total} records matched, only the first {shown} are listed above."


def render_limitations(notes: list[str]) -> str:
    """The block appended to the context text, or '' when nothing is missing."""
    if not notes:
        return ""
    return (
        f"\n\n{SECTION_HEADING}:\n"
        + "\n".join(f"- {note}" for note in notes)
        + "\nNo matching records means the retrieved data does not show it; it does not prove"
          " the university does not offer it."
    )


def _entity_name(mask: str, entities: EntityMap) -> str:
    """Readable name for an entity mask, falling back to the mask itself."""
    entity = entities.get(mask)
    if entity is None:
        return mask
    if isinstance(entity, CourseEntity):
        return entity.normalized
    return entity.canonical
