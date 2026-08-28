from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AccountCreate(BaseModel):
    name: str = "未命名账号"
    cookie: str = Field(min_length=1)
    domain: str | None = None
    profileId: int | None = None
    semesterId: int | None = None
    should_validate: bool = Field(default=True, alias="validate")


class AccountUpdate(BaseModel):
    name: str | None = None
    cookie: str | None = Field(default=None, min_length=1)
    domain: str | None = None
    profileId: int | None = None
    semesterId: int | None = None


class TargetGroupIn(BaseModel):
    name: str = Field(min_length=1)
    limit: int = 1
    courseNos: list[str] = Field(default_factory=list)

    @field_validator("courseNos")
    @classmethod
    def normalize_course_numbers(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


class TargetsUpdate(BaseModel):
    groups: list[TargetGroupIn]


class SettingsUpdate(BaseModel):
    domain: str | None = None
    profileId: int | None = None
    semesterId: int | None = None
    startTime: dt.datetime | None = None
    skipPre: bool | None = None


class TaskCreate(BaseModel):
    accountIds: list[str] = Field(min_length=1)
    startTime: dt.datetime
    skipPrecheck: bool = False


class ApiEnvelope(BaseModel):
    code: int | str = 0
    message: str = "ok"
    data: Any = None


TaskStatus = Literal["scheduled", "running", "completed", "failed", "stopped"]
