from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewRequest(StrictModel):
    action: Literal["approved", "rejected", "pending"]
    sql: str | None = Field(default=None, max_length=20_000)
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=3, max_length=2000)
    revision: int = Field(ge=0)


class ValidateRequest(StrictModel):
    sql: str = Field(min_length=1, max_length=20_000)


class RunConfig(StrictModel):
    name: str = Field(default="Paired evaluation", min_length=1, max_length=80)
    split: Literal["development", "holdout"] = "holdout"
    provider: Literal["demo", "openai"] = "demo"
    model: str = Field(default="", max_length=120)
    concurrency: int = Field(default=2, ge=1, le=4)
    few_shot_limit: int = Field(default=6, ge=1, le=12)
    max_requests: int = Field(default=240, ge=1, le=1000)
    max_output_tokens: int = Field(default=1024, ge=128, le=4096)


class ResumeRequest(StrictModel):
    extra_requests: int = Field(default=0, ge=0, le=1000)
