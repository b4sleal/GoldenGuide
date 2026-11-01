"""Public citation references, shared by generation and the projection of older saved answers."""
from urllib.parse import urlsplit

from backend.domain.entities.answer_content import (
    AnswerCitationBlock,
    AnswerContentBlock,
)
from backend.domain.entities.conversations import ChatMessagePublic
from backend.domain.entities.ingestion_types import KnowledgeSourceType
from backend.domain.settings.ai_behavior import RAGSource

REGISTRATION_TITLE = "LORIS - Registration"
REGISTRATION_TYPES = frozenset({"course_terms", KnowledgeSourceType.LORIS_REGISTRATION.value})


def is_registration_source(source: RAGSource, registration_url: str) -> bool:
    if source.source_type in REGISTRATION_TYPES:
        return True
    # Legacy entries may lack a type. Match the configured entry point, not every university URL.
    try:
        url, registration = urlsplit(source.url or ""), urlsplit(registration_url)
        return (url.scheme, url.netloc, url.path.rstrip("/")) == (
            registration.scheme, registration.netloc, registration.path.rstrip("/"),
        )
    except ValueError:
        return False


def registration_source(registration_url: str) -> RAGSource:
    return RAGSource(title=REGISTRATION_TITLE, url=registration_url, source_type="course_terms")


def normalize_history_sources(message: ChatMessagePublic, registration_url: str) -> ChatMessagePublic:
    """Consolidate legacy references on read without rewriting the stored evidence or diagnostics.

    Source positions are citation IDs. Rebuild that mapping together with the list so a Calendar
    citation following duplicate LORIS entries never starts pointing at a different source.
    """
    if not message.sources:
        return message
    sources: list[RAGSource] = []
    numbers: dict[int, int] = {}
    registration_number: int | None = None
    for old_number, source in enumerate(message.sources, 1):
        if is_registration_source(source, registration_url):
            if registration_number is None:
                sources.append(registration_source(registration_url))
                registration_number = len(sources)
            numbers[old_number] = registration_number
        else:
            sources.append(source)
            numbers[old_number] = len(sources)

    if sources == message.sources:
        return message
    content = message.answer_content
    if content is not None:
        blocks: list[AnswerContentBlock] = []
        for block in content.blocks:
            if isinstance(block, AnswerCitationBlock):
                mapped = list(dict.fromkeys(numbers[n] for n in block.source_nums if n in numbers))
                if mapped:
                    blocks.append(AnswerCitationBlock(
                        source_nums=mapped, urls=[sources[n - 1].url for n in mapped],
                    ))
            else:
                blocks.append(block)
        content = content.model_copy(update={"blocks": blocks})
    return message.model_copy(update={"sources": sources, "answer_content": content})
