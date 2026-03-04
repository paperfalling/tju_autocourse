import time


_DEFAULT_META = {
    "profileId": 0,
    "semesterId": 0,
    "domain": "classes.tju.edu.cn",
    "startTime": "1970-01-01T08:00:00",
    "skipPre": False,
}

_config_meta = _DEFAULT_META.copy()


def _expect_type(value: object, expected_type: type, field_name: str) -> None:
    if not isinstance(value, expected_type):
        raise ValueError(
            f"配置项 `{field_name}` 类型错误，应为 {expected_type.__name__}"
        )


def _validate_time(time_string: str, field_name: str) -> None:
    try:
        time.strptime(time_string, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            f"配置项 `{field_name}` 时间格式错误，应为 YYYY-MM-DDTHH:MM:SS"
        ) from exc


def validate_meta(meta: dict) -> None:
    _expect_type(meta, dict, "meta")
    required_fields = ["domain", "profileId", "semesterId", "startTime", "skipPre"]
    for field in required_fields:
        if field not in meta:
            raise ValueError(f"配置项 `meta.{field}` 缺失")
    _expect_type(meta["domain"], str, "meta.domain")
    if not meta["domain"].strip():
        raise ValueError("配置项 `meta.domain` 不能为空")
    _expect_type(meta["profileId"], int, "meta.profileId")
    _expect_type(meta["semesterId"], int, "meta.semesterId")
    _expect_type(meta["startTime"], str, "meta.startTime")
    _validate_time(meta["startTime"], "meta.startTime")
    _expect_type(meta["skipPre"], bool, "meta.skipPre")


def validate_user_config(config: dict) -> None:
    _expect_type(config, dict, "user")
    required_fields = ["name", "cookie", "tags_sort_limit", "courses"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"用户配置项 `{field}` 缺失")
    _expect_type(config["name"], str, "user.name")
    _expect_type(config["cookie"], str, "user.cookie")
    _expect_type(config["tags_sort_limit"], dict, "user.tags_sort_limit")
    _expect_type(config["courses"], dict, "user.courses")
    for tag, limit in config["tags_sort_limit"].items():
        _expect_type(tag, str, "user.tags_sort_limit.<tag>")
        _expect_type(limit, int, f"user.tags_sort_limit.{tag}")
        if tag not in config["courses"]:
            raise ValueError(f"用户配置项 `courses.{tag}` 缺失")
    for tag, courses in config["courses"].items():
        _expect_type(tag, str, "user.courses.<tag>")
        _expect_type(courses, list, f"user.courses.{tag}")
        for course_no in courses:
            _expect_type(course_no, str, f"user.courses.{tag}[]")
    optional_fields = {
        "profileId": int,
        "semesterId": int,
        "domain": str,
        "startTime": str,
        "skipPre": bool,
    }
    for field, expected_type in optional_fields.items():
        if (
            field in config
            and config[field] is not None
            and not isinstance(config[field], expected_type)
        ):
            raise ValueError(
                f"用户配置项 `{field}` 类型错误，应为 {expected_type.__name__}"
            )
    if (
        "domain" in config
        and isinstance(config["domain"], str)
        and not config["domain"].strip()
    ):
        raise ValueError("用户配置项 `domain` 不能为空")
    if "startTime" in config and isinstance(config["startTime"], str):
        _validate_time(config["startTime"], "user.startTime")


def validate_config(config: dict) -> None:
    _expect_type(config, dict, "config")
    if "meta" not in config:
        raise ValueError("配置项 `meta` 缺失")
    if "users" not in config:
        raise ValueError("配置项 `users` 缺失")
    validate_meta(config["meta"])
    _expect_type(config["users"], list, "users")
    if not config["users"]:
        raise ValueError("配置项 `users` 不能为空")
    for user_config in config["users"]:
        validate_user_config(user_config)


def set_config_meta(meta: dict) -> None:
    validate_meta(meta)
    _config_meta.update(meta)


def merge_user_config(config: dict) -> dict:
    merged_config = config.copy()
    for key, value in _config_meta.items():
        merged_config.setdefault(key, value)
    validate_user_config(merged_config)
    return merged_config
