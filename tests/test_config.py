import copy

import pytest

from tju_autocourse.config import ConfigError, parse_config, read_config


def user(**overrides):
    return {
        "auth": {"type": "cookie", "cookie": "secret-cookie"},
        "targets": [{"group_name": "g", "limit": 1, "courses": ["001"]}],
    } | overrides


def test_inheritance_replaces_whole_response_rule_and_preserves_false():
    raw = {
        "meta": {
            "profileId": 9,
            "skipPre": True,
            "selection_policy": {
                "full": {"action": "retry", "max_retries": 3},
                "unknown": "stop",
            },
        },
        "users": [
            user(
                skipPre=False,
                targets=[
                    {
                        "group_name": "g",
                        "limit": 1,
                        "courses": ["001"],
                        "selection_policy": {"full": "retry"},
                    }
                ],
            ),
            user(selection_policy={"full": "skip"}),
        ],
    }
    original = copy.deepcopy(raw)
    first, second = parse_config(raw).users
    assert raw == original
    assert first.profileId == 9 and first.skipPre is False
    assert first.selection_policy.full.max_retries == 3
    assert first.targets[0].selection_policy.full.max_retries is None
    assert first.targets[0].selection_policy.unknown.action == "stop"
    assert second.targets[0].selection_policy.full.action == "skip"
    assert parse_config({"users": [user()]}).users[0].profileId == 0


@pytest.mark.parametrize(
    "rule",
    [
        "invalid",
        {"action": "retry", "max_retries": -1},
        {"action": "skip", "max_retries": 2},
        {"action": "retry", "on_exhausted": "skip"},
        {"action": "retry", "max_retries": 2, "on_exhausted": "retry"},
        {"action": "retry", "max_retries": True},
    ],
)
def test_invalid_policy_rejected(rule):
    with pytest.raises(ConfigError):
        parse_config({"users": [user(selection_policy={"full": rule})]})


@pytest.mark.parametrize(
    "auth",
    [
        {"type": "sso", "username": "student"},
        {"type": "cookie", "cookie": ""},
        {"type": "cookie", "cookie": "x=y", "retries": 1},
        {"type": "sso", "username": "u", "password": "p", "retries": -1},
        {"type": "other", "password": "topsecret"},
    ],
)
def test_auth_validation_does_not_leak_secrets(auth):
    with pytest.raises(ConfigError) as captured:
        parse_config({"users": [user(auth=auth)]})
    assert "topsecret" not in str(captured.value)


def test_current_auth_format_and_secret_repr():
    config = parse_config({"users": [user()]})
    assert "secret-cookie" not in repr(config)


@pytest.mark.parametrize(
    "raw",
    [
        {"users": []},
        {"users": [user(targets=None)]},
        {"users": [user(selection_policy={"success": "skip"})]},
        {"users": [user(name="../secret")]},
        {"meta": {"domain": "https://example.org"}, "users": [user()]},
    ],
)
def test_invalid_structure_and_unsupported_rules(raw):
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_naive_datetime_stays_naive_and_auth_defaults(make_config):
    config = make_config(
        startTime="2026-09-01T12:00:00",
        auth={"type": "sso", "username": "u", "password": "p"},
    )
    assert config.startTime.tzinfo is None
    assert config.auth.retries == 2


def test_bad_yaml_error_does_not_echo_contents(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('password: "topsecret', encoding="utf-8")
    with pytest.raises(ConfigError) as captured:
        read_config(path)
    assert "topsecret" not in str(captured.value)


def test_numeric_course_identifiers_require_explicit_correction():
    with pytest.raises(ConfigError, match="前导零"):
        parse_config(
            {
                "users": [
                    user(
                        targets=[
                            {
                                "group_name": "g",
                                "limit": 1,
                                "courses": [2058, 2059, "06306"],
                            }
                        ]
                    )
                ]
            }
        )
