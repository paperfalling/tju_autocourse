import time
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class TargetConfig(BaseModel):
    group_name: str
    limit: int
    courses: List[str]


class MetaConfig(BaseModel):
    domain: str = Field(min_length=1)
    profileId: int
    semesterId: int
    startTime: str
    skipPre: bool

    @field_validator("startTime")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            time.strptime(v, "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise ValueError("时间格式错误，应为 YYYY-MM-DDTHH:MM:SS") from exc
        return v


class UserConfig(BaseModel):
    name: str
    cookie: str
    targets: List[TargetConfig]
    profileId: Optional[int] = None
    semesterId: Optional[int] = None
    domain: Optional[str] = Field(None, min_length=1)
    startTime: Optional[str] = None
    skipPre: Optional[bool] = None

    @field_validator("startTime")
    @classmethod
    def validate_time(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                time.strptime(v, "%Y-%m-%dT%H:%M:%S")
            except ValueError as exc:
                raise ValueError("时间格式错误，应为 YYYY-MM-DDTHH:MM:SS") from exc
        return v


class AppConfig(BaseModel):
    meta: MetaConfig
    users: List[UserConfig]


_DEFAULT_META = {
    "profileId": 0,
    "semesterId": 0,
    "domain": "classes.tju.edu.cn",
    "startTime": "1970-01-01T08:00:00",
    "skipPre": False,
}

_config_meta = _DEFAULT_META.copy()


def validate_meta(meta: dict) -> None:
    MetaConfig.model_validate(meta)


def validate_user_config(config: dict) -> None:
    UserConfig.model_validate(config)


def validate_config(config: dict) -> None:
    AppConfig.model_validate(config)
    if not config.get("users"):
        raise ValueError("配置项 `users` 不能为空")


def set_config_meta(meta: dict) -> None:
    validate_meta(meta)
    _config_meta.update(meta)


def merge_user_config(config: dict) -> dict:
    merged_config = config.copy()
    for key, value in _config_meta.items():
        merged_config.setdefault(key, value)
    validate_user_config(merged_config)
    return merged_config
