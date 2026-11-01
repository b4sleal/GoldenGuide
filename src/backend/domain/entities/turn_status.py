"""Progress of one answer, streamed before its text so the student sees what is happening.

Statuses carry codes, never display text: the client owns the wording ("Searching LORIS registration...").
Each one reflects real work, taken from the validated plan, never guessed from the question.
"""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from backend.domain.entities.retrieval_plan import RetrievalSource


class TurnStage(StrEnum):
    UNDERSTANDING = "understanding"   # Entity extraction and the router's plan.
    SEARCHING = "searching"           # One per source the plan searches.
    WRITING = "writing"               # The answer model has started.


class TurnStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: TurnStage
    # Set for SEARCHING: courses (Academic Calendar), course_terms (LORIS), wlu_pages (programs), vector.
    source: RetrievalSource | None = None
