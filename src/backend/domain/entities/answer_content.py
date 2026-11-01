"""Durable answer content, independent of transport events and retrieval diagnostics.

Only what was displayed belongs here. Progress, terminal events and internal errors are not replayed
from history; the stored message status determines whether the answer completed.
"""
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class AnswerTextBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text"] = "text"
    text: str


class AnswerCitationBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["citation"] = "citation"
    source_nums: list[PositiveInt]
    urls: list[str | None]

    @model_validator(mode="after")
    def _matching_urls(self) -> Self:
        if len(self.source_nums) != len(self.urls):
            raise ValueError("Each citation number needs a corresponding URL (or null)")
        return self


class AnswerTableBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["table"] = "table"
    title: str
    columns: list[str]
    rows: list[list[str]]


type AnswerContentBlock = Annotated[
    AnswerTextBlock | AnswerCitationBlock | AnswerTableBlock, Field(discriminator="type")
]


class StoredAnswerContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Persist the shape version so future changes can distinguish already-saved answers.
    version: Literal[1] = 1
    blocks: list[AnswerContentBlock] = Field(default_factory=list)
