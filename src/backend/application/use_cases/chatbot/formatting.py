"""Turn [Source n] citations in the streamed answer into citation events, across chunk boundaries."""
import re

from backend.domain.settings.ai_behavior import RAGSource


CITATION_PATTERN = re.compile(
    r"\[Source\s+(\d+(?:\s*,\s*\d+)*)\s*\]",
    re.IGNORECASE,
)

POSSIBLE_CITATION = re.compile(
    r"\[(?:S(?:o(?:u(?:r(?:c(?:e)?)?)?)?)?)?"
    r"(?:\s+\d[\d,\s]*)?\Z",
    re.IGNORECASE,
)


class CitationStreamParser:
    def __init__(self, sources: list[RAGSource]):
        self.sources = sources
        self.buffer = ""

    def _citation_event(self, match: re.Match) -> dict:
        numbers = list(dict.fromkeys(
            int(n)
            for n in re.findall(r"\d+", match.group(1))
            if 1 <= int(n) <= len(self.sources)
        ))

        if not numbers:
            return {
                "type": "text",
                "text": match.group(0),
            }

        return {
            "type": "citation",
            "source_nums": numbers,
            "urls": [
                self.sources[n - 1].url
                for n in numbers
            ],
        }

    def feed(self, chunk: str) -> list[dict]:
        self.buffer += chunk
        events = []

        while self.buffer:
            match = CITATION_PATTERN.search(self.buffer)

            if match:
                if match.start():
                    events.append({
                        "type": "text",
                        "text": self.buffer[:match.start()],
                    })

                events.append(self._citation_event(match))
                self.buffer = self.buffer[match.end():]
                continue

            # Find the earliest possible incomplete citation.
            hold_from = len(self.buffer)

            for index, char in enumerate(self.buffer):
                if char != "[":
                    continue

                candidate = self.buffer[index:]

                if POSSIBLE_CITATION.fullmatch(candidate):
                    hold_from = index
                    break

            if hold_from:
                events.append({
                    "type": "text",
                    "text": self.buffer[:hold_from],
                })
                self.buffer = self.buffer[hold_from:]

            # Keep only a potential unfinished citation.
            break

        return events

    def flush(self) -> list[dict]:
        events = self.feed("")

        if self.buffer:
            events.append({
                "type": "text",
                "text": self.buffer,
            })
            self.buffer = ""

        return events