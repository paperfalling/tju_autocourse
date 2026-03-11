import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TargetConfig(BaseModel):
    group_name: str
    limit: int
    courses: List[str]


class MetaConfig(BaseModel):
    domain: str = Field(default="classes.tju.edu.cn")
    profileId: int = 0
    semesterId: int = 0
    startTime: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.strptime(
            "1970-01-01T08:00:00", "%Y-%m-%dT%H:%M:%S"
        )
    )
    skipPre: bool = False


class UserConfig(BaseModel):
    name: str
    cookie: str
    targets: List[TargetConfig]
    profileId: Optional[int] = None
    semesterId: Optional[int] = None
    domain: Optional[str] = None
    startTime: Optional[datetime.datetime] = None
    skipPre: Optional[bool] = None


class AppConfig(BaseModel):
    meta: MetaConfig
    users: List[UserConfig]


_DEFAULT_META = {
    "profileId": 0,
    "semesterId": 0,
    "domain": "classes.tju.edu.cn",
    "startTime": datetime.datetime(1970, 1, 1, 8, 0, 0),
    "skipPre": False,
}

_config_meta = _DEFAULT_META.copy()


def validate_user_config(config: dict) -> None:
    UserConfig.model_validate(config)


def validate_config(config: dict) -> None:
    AppConfig.model_validate(config)
    if not config.get("users"):
        raise ValueError("配置项 `users` 不能为空")


def set_config_meta(meta: dict) -> None:
    MetaConfig.model_validate(meta)
    _config_meta.update(meta)


def merge_user_config(config: dict) -> dict:
    merged_config = config.copy()
    for key, value in _config_meta.items():
        merged_config.setdefault(key, value)
    validate_user_config(merged_config)
    return merged_config
