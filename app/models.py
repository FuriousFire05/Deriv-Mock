from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, strict=True)
]


class TriageRequest(BaseModel):
    message: NonEmptyString


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["deposit", "withdrawal", "account", "trading", "technical", "other"]
    priority: Literal["low", "medium", "high", "critical"]
    summary: NonEmptyString
    recommended_action: NonEmptyString
    requires_human: bool
