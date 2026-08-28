import datetime

from pydantic import BaseModel, Field, model_validator


class TargetConfig(BaseModel):
    group_name: str
    limit: int
    courses: list[str]


class MetaConfig(BaseModel):
    domain: str = Field(default="classes.tju.edu.cn")
    profileId: int = 0
    semesterId: int = 0
    startTime: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime(
            1970, 1, 1, 8, 0, 0, tzinfo=datetime.UTC
        )
    )
    skipPre: bool = False


class UserConfig(BaseModel):
    name: str = "user"
    cookie: str | None = None
    username: str | None = None
    password: str | None = None
    account: str | None = None
    targets: list[TargetConfig]
    profileId: int | None = None
    semesterId: int | None = None
    domain: str | None = None
    startTime: datetime.datetime | None = None
    skipPre: bool | None = None

    @model_validator(mode="after")
    def validate_authentication(self) -> "UserConfig":
        if not self.cookie and not (self.password and (self.username or self.account)):
            raise ValueError("provide cookie or username/password credentials")
        return self


class AppConfig(BaseModel):
    meta: MetaConfig
    users: list[UserConfig]


_DEFAULT_META = {
    "profileId": 0,
    "semesterId": 0,
    "domain": "classes.tju.edu.cn",
    "startTime": datetime.datetime(1970, 1, 1, 8, 0, 0, tzinfo=datetime.UTC),
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
