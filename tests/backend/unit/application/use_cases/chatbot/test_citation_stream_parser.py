
from backend.application.use_cases.chatbot.formatting import (
    CitationStreamParser,
)
from backend.domain.settings.ai_behavior import RAGSource


def test_streamed_grouped_citation():
    sources = [
        RAGSource(title=f"Section {i}", url=None)
        for i in range(1, 15)
    ]

    parser = CitationStreamParser(sources)

    events = []

    for chunk in [
        "Prerequisites [Sou",
        "rce 1, 2, 3, 4, 5, 6, ",
        "7, 8, 9, 10, 11, 12, 13, 14]",
    ]:
        events.extend(parser.feed(chunk))

    events.extend(parser.flush())

    citations = [
        event for event in events
        if event["type"] == "citation"
    ]

    assert len(citations) == 1
    assert citations[0]["source_nums"] == list(range(1, 15))
    assert citations[0]["urls"] == [None] * 14


def test_regular_markdown_is_preserved():
    parser = CitationStreamParser([])

    events = parser.feed("Use [LORIS](https://example.com).")
    events.extend(parser.flush())

    result = "".join(
        event["text"]
        for event in events
        if event["type"] == "text"
    )

    assert result == "Use [LORIS](https://example.com)."
