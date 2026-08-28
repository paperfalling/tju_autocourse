from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from web_api.config_store import ConfigStore
from web_api.main import create_app
from web_api.services import WebUser, create_web_users


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path / "config.yaml", serve_frontend=False)
    return TestClient(app)


def test_health_and_empty_accounts(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        health = client.get("/api/v1/health")
        accounts = client.get("/api/v1/accounts")

    assert health.status_code == 200
    assert health.json()["data"] == {"status": "ok"}
    assert accounts.json()["data"] == []


def test_account_cookie_is_never_returned(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/accounts",
            json={
                "name": "测试用户",
                "cookie": "JSESSIONID=very-secret-value; semester.id=116",
                "profileId": 3820,
                "semesterId": 116,
                "validate": False,
            },
        )
        listed = client.get("/api/v1/accounts")

    assert response.status_code == 201
    serialized = response.text + listed.text
    assert "very-secret-value" not in serialized
    assert response.json()["data"]["cookieMasked"].startswith("JSESSIONID=")


def test_target_groups_round_trip(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/accounts",
            json={
                "name": "测试用户",
                "cookie": "test-cookie",
                "profileId": 3820,
                "semesterId": 116,
                "validate": False,
            },
        )
        saved = client.put(
            "/api/v1/accounts/account-0/targets",
            json={"groups": [{"name": "体育", "limit": 1, "courseNos": ["06488", "06491"]}]},
        )
        loaded = client.get("/api/v1/accounts/account-0/targets")

    assert saved.status_code == 200
    assert loaded.json()["data"][0]["name"] == "体育"
    assert loaded.json()["data"][0]["courseNos"] == ["06488", "06491"]


def test_settings_round_trip(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.put(
            "/api/v1/settings",
            json={"domain": "classes.tju.edu.cn", "skipPre": True},
        )
        loaded = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert loaded.json()["data"]["skipPre"] is True


def test_cookie_masking() -> None:
    assert ConfigStore.mask_cookie("JSESSIONID=abcdefgh") == "JSESSIONID=••••••••efgh"
    assert ConfigStore.mask_cookie("") == "未设置"


def test_null_meta_and_user_values_fall_back_to_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "meta": {"domain": "classes.tju.edu.cn", "skipPre": None},
                "users": [{
                    "name": "测试用户",
                    "cookie": "test-cookie",
                    "skipPre": None,
                    "targets": [],
                }],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    store = ConfigStore(config_path)

    assert store.load()["meta"]["skipPre"] is False
    assert store.resolved_account("account-0")["skipPre"] is False


def test_web_user_prepare_uses_tolerant_course_loader(monkeypatch) -> None:
    course = {
        "id": "1",
        "no": "06488",
        "name": "测试课程",
        "code": "TEST001",
        "arrangement": [],
    }

    async def fake_courses(user, session):
        del user, session
        return [course]

    async def fake_status(self, session):
        del self, session
        return {"1": {"sc": 0, "lc": 10}}

    async def fake_done(self, session):
        del self, session
        return []

    monkeypatch.setattr("web_api.services.fetch_course_info_tolerant", fake_courses)
    monkeypatch.setattr(WebUser, "query_status", fake_status)
    monkeypatch.setattr(WebUser, "query_done", fake_done)

    users = create_web_users(
        [{
            "name": "测试用户",
            "cookie": "test-cookie",
            "profileId": 3820,
            "semesterId": 116,
            "domain": "classes.tju.edu.cn",
            "startTime": dt.datetime(2099, 1, 1, 8, 0, 0),
            "skipPre": False,
            "targets": [{"group_name": "测试组", "limit": 1, "courses": ["06488"]}],
        }]
    )
    asyncio.run(users[0].prepare())

    assert users[0].config.courses_info == [course]
    assert users[0].scheduler is not None
