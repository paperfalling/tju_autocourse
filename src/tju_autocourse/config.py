"""Validated configuration; inheritance is resolved without global state."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)


class ConfigError(ValueError):
    """A configuration error safe to display without credentials."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Rule(Model):
    action: Literal["retry", "skip", "stop"]
    max_retries: int | None = Field(default=None, ge=0, strict=True)
    on_exhausted: Literal["skip", "stop"] = "skip"

    @model_validator(mode="before")
    @classmethod
    def expand(cls, value):
        return {"action": value} if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_fields(self):
        if self.action != "retry" and self.model_fields_set & {
            "max_retries",
            "on_exhausted",
        }:
            raise ValueError("retry options require action: retry")
        if "on_exhausted" in self.model_fields_set and self.max_retries is None:
            raise ValueError("on_exhausted requires a finite max_retries")
        return self


class SelectionPolicy(Model):
    not_open: Rule = Rule(action="retry")
    too_fast: Rule = Rule(action="retry")
    full: Rule = Rule(action="skip")
    already_selected: Rule = Rule(action="skip")
    unknown: Rule = Rule(action="skip")


class CookieAuth(Model):
    type: Literal["cookie"]
    cookie: SecretStr

    @field_validator("cookie")
    @classmethod
    def nonempty(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("cookie cannot be empty")
        return value


class SsoAuth(Model):
    type: Literal["sso"]
    username: SecretStr
    password: SecretStr
    retries: int = Field(default=2, ge=0, strict=True)

    @field_validator("username", "password")
    @classmethod
    def nonempty(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("SSO credentials cannot be empty")
        return value


AuthConfig = Annotated[CookieAuth | SsoAuth, Field(discriminator="type")]


class TargetConfig(Model):
    group_name: str
    limit: int = Field(ge=-1, strict=True)
    courses: list[str]
    selection_policy: SelectionPolicy = Field(default_factory=SelectionPolicy)

    @field_validator("courses", mode="before")
    @classmethod
    def string_identifiers(cls, value):
        if isinstance(value, list) and any(
            not isinstance(number, str) for number in value
        ):
            raise ValueError(
                '课程序号必须是带引号的字符串，例如 "02058"；数字类型可能已丢失前导零，请按实际课程序号修正'
            )
        return value


class MetaConfig(Model):
    domain: str = "classes.tju.edu.cn"
    profileId: int = Field(default=0, ge=0)
    semesterId: int = Field(default=0, ge=0)
    startTime: dt.datetime = dt.datetime(1970, 1, 1, 8)
    skipPre: bool = False
    selection_policy: SelectionPolicy = Field(default_factory=SelectionPolicy)

    @field_validator("domain")
    @classmethod
    def hostname_only(cls, value):
        import re

        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
            raise ValueError("domain must be a hostname without a scheme or path")
        return value


class UserConfig(MetaConfig):
    name: str = "user"
    auth: AuthConfig
    targets: list[TargetConfig] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def safe_name(cls, value):
        if (
            not value.strip()
            or value in {".", ".."}
            or any(c in value for c in '/\\<>:"|?*')
        ):
            raise ValueError("name must be a nonempty safe filename component")
        return value

    @model_validator(mode="before")
    @classmethod
    def resolve_groups(cls, value):
        if not isinstance(value, dict):
            return value
        resolved = dict(value)
        if not isinstance(value.get("targets", []), list):
            return resolved
        policy = value.get("selection_policy", {})
        if isinstance(policy, SelectionPolicy):
            policy = policy.model_dump(exclude_unset=True)
        groups = []
        for group in value.get("targets", []):
            if isinstance(group, dict) and isinstance(policy, dict):
                group = dict(group)
                overrides = group.get("selection_policy", {})
                if isinstance(overrides, dict):
                    group["selection_policy"] = policy | overrides
            groups.append(group)
        resolved["targets"] = groups
        return resolved


class AppConfig(Model):
    meta: MetaConfig = Field(default_factory=MetaConfig)
    users: list[UserConfig] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def resolve_users(cls, value):
        if not isinstance(value, dict):
            return value
        meta = value.get("meta", {})
        if not isinstance(meta, dict) or not isinstance(value.get("users"), list):
            return value
        users = []
        for index, user in enumerate(value["users"], 1):
            if not isinstance(user, dict):
                users.append(user)
                continue
            merged = meta | user
            if not merged.get("name"):
                merged["name"] = f"user{index}"
            policy = meta.get("selection_policy", {})
            overrides = user.get("selection_policy", {})
            if isinstance(policy, dict) and isinstance(overrides, dict):
                merged["selection_policy"] = policy | overrides
            users.append(merged)
        return value | {"users": users}


def parse_config(raw: object) -> AppConfig:
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        messages = [
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
            for e in exc.errors(include_input=False, include_context=False)
        ]
        raise ConfigError("配置错误: " + "; ".join(messages)) from None


def read_config(path: str | Path) -> dict:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ConfigError("配置 YAML 无法解析，请检查格式") from None
    if not isinstance(raw, dict):
        raise ConfigError("配置必须为 YAML 映射")
    return raw


def load_config(path: str | Path) -> AppConfig:
    return parse_config(read_config(path))
