import datetime

from pydantic import BaseModel, Field, model_validator


class TargetConfig(BaseModel):
    group_name: str
    limit: int
    courses: list[str]


class MetaConfig(BaseModel):
    domain: str = "classes.tju.edu.cn"
    profileId: int = 0
    semesterId: int = 0
    startTime: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime(
            1970, 1, 1, 8, 0, 0, tzinfo=datetime.UTC
        )
    )
    skipPre: bool = False
    request_interval: float = Field(default=0.5, gt=0)
    auth_retries: int = Field(default=2, ge=0)
    too_fast_retries: int = Field(default=2, ge=0)


class UserConfig(MetaConfig):
    name: str = "user"
    cookie: str | None = None
    username: str | None = None
    password: str | None = None
    targets: list[TargetConfig]

    @model_validator(mode="after")
    def validate_authentication(self) -> "UserConfig":
        if not self.cookie and not (self.username and self.password):
            raise ValueError("provide cookie or username/password credentials")
        return self

    @property
    def headers(self) -> dict:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
            "Origin": f"https://{self.domain}",
            "x-requested-with": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": f"https://{self.domain}/eams/stdElectCourse!defaultPage.action",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers


class AppConfig(BaseModel):
    meta: MetaConfig
    users: list[UserConfig]


_DEFAULT_META = MetaConfig().model_dump()
_config_meta = _DEFAULT_META.copy()


def validate_config(config: dict) -> None:
    AppConfig.model_validate(config)
    if not config.get("users"):
        raise ValueError("configuration field `users` cannot be empty")


def set_config_meta(meta: dict) -> None:
    _config_meta.update(MetaConfig.model_validate(meta).model_dump())


def merge_user_config(config: dict) -> dict:
    merged_config = _config_meta | config
    return UserConfig.model_validate(merged_config).model_dump()
