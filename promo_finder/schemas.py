"""JSON shapes the LLMs must return. Invalid replies are rejected and retried."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Segment(BaseModel):
    start: str | float
    end: str | float


class CandidateOut(BaseModel):
    title: str = Field(description="3-6 word working title")
    segments: list[Segment] = Field(min_length=1, max_length=4)
    hook_line: str
    cliffhanger_line: str
    open_question: str
    archetype: str
    why: str


class CandidatesOut(BaseModel):
    promos: list[CandidateOut]


class ColdViewer(BaseModel):
    who: str
    what: str
    want_next: str
    understood: bool
    clarity: int = Field(ge=1, le=10)


class ThreeSec(BaseModel):
    stop: bool
    score: int = Field(ge=1, le=10)
    why: str


class Cliff(BaseModel):
    unresolved: bool
    score: int = Field(ge=1, le=10)


class Outcome(BaseModel):
    outcome: str
    p: float = Field(ge=0, le=1)


class AdRisk(BaseModel):
    level: Literal["low", "medium", "high"]
    reason: str

    @field_validator("level", mode="before")
    @classmethod
    def _lower(cls, v):
        return str(v).lower().strip()


class JudgeClip(BaseModel):
    id: str
    cold_viewer: ColdViewer
    three_sec: ThreeSec
    cliffhanger: Cliff
    outcomes: list[Outcome] = Field(min_length=2, max_length=6)
    ad_risk: AdRisk


class JudgeOut(BaseModel):
    clips: list[JudgeClip]
