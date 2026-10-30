"""The institution GoldenGuide serves: identity and locale facts that code must never hardcode."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class InstitutionProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1, description="Value stored in courses.institution, e.g. WLU.")
    timezone: str = Field(description="IANA zone that defines 'today' for terms and deadlines.")
    registration_url: HttpUrl = Field(description="Registration entry point cited for term sections.")

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        # Fail at startup, not on the first question that needs today's date.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
