import pytest

import tju_autocourse as atc
from tju_autocourse.models import UserConfig


def _target():
    return {"group_name": "required", "limit": 1, "courses": ["10001"]}


def _meta(**overrides):
    value = {
        "domain": "classes.tju.edu.cn",
        "profileId": 1,
        "semesterId": 2,
        "startTime": "1970-01-01T08:00:00",
        "skipPre": False,
    }
    value.update(overrides)
    return value


def test_user_config_accepts_cookie_and_builds_cookie_header():
    config = UserConfig.model_validate(_meta(cookie="cookie=test", targets=[_target()]))
    assert config.headers["Cookie"] == "cookie=test"


def test_user_config_accepts_credentials_without_cookie():
    config = UserConfig.model_validate(
        _meta(username="student", password="secret", targets=[_target()])
    )
    assert "Cookie" not in config.headers


def test_user_config_requires_one_authentication_method():
    with pytest.raises(ValueError, match="username/password"):
        UserConfig.model_validate(_meta(targets=[_target()]))


def test_account_is_not_an_authentication_alias():
    with pytest.raises(ValueError, match="username/password"):
        UserConfig.model_validate(
            _meta(account="student", password="secret", targets=[_target()])
        )


def test_request_interval_must_be_positive():
    with pytest.raises(ValueError):
        UserConfig.model_validate(
            _meta(cookie="cookie=test", request_interval=0, targets=[_target()])
        )


def test_auth_retries_default_and_must_be_nonnegative():
    config = UserConfig.model_validate(_meta(cookie="cookie=test", targets=[_target()]))
    assert config.auth_retries == 2

    with pytest.raises(ValueError):
        UserConfig.model_validate(
            _meta(cookie="cookie=test", auth_retries=-1, targets=[_target()])
        )

    assert config.too_fast_retries == 2
    with pytest.raises(ValueError):
        UserConfig.model_validate(
            _meta(cookie="cookie=test", too_fast_retries=-1, targets=[_target()])
        )


def test_user_values_override_global_defaults_without_mutating_other_users():
    atc.set_config_meta(_meta(profileId=100, semesterId=200))
    first = atc.create_user({"cookie": "cookie=a", "targets": [_target()]})
    second = atc.create_user(
        {
            "cookie": "cookie=b",
            "profileId": 999,
            "skipPre": True,
            "targets": [_target()],
        }
    )

    assert first.config.profileId == 100
    assert first.config.semesterId == 200
    assert second.config.profileId == 999
    assert second.config.skipPre is True


def test_global_config_requires_at_least_one_user():
    with pytest.raises(ValueError):
        atc.api.validate_config({"meta": _meta(), "users": []})
