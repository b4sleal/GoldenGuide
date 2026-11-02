
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


def stream(sources: int, *chunks: str) -> list[dict]:
    parser = CitationStreamParser([RAGSource(title=f"S{i}", url=f"https://www.wlu.ca/{i}") for i in range(1, sources + 1)])
    events = [event for chunk in chunks for event in parser.feed(chunk)]
    return events + parser.flush()


def test_bare_numeric_citations_from_the_prompt_are_recognized_across_chunks():
    events = stream(3, "Lab instructor [", "1]. Office N2091 [2, ", "3].")

    assert [event["source_nums"] for event in events if event["type"] == "citation"] == [[1], [2, 3]]
    assert "".join(event["text"] for event in events if event["type"] == "text") == "Lab instructor . Office N2091 ."


def test_bracketed_numbers_that_are_not_sources_stay_text():
    events = stream(2, "Founded in [1911] and renamed [2024].")

    assert [event["type"] for event in events if event["type"] == "citation"] == []
    assert "".join(event["text"] for event in events) == "Founded in [1911] and renamed [2024]."


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
