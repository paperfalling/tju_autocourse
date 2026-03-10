import asyncio
import aiohttp
import pytest
import tju_autocourse as atc


def _base_user_config() -> dict:
    return {
        "name": "tester",
        "cookie": "cookie=test",
        "profileId": 1,
        "semesterId": 2,
        "domain": "classes.tju.edu.cn",
        "startTime": "1970-01-01T08:00:00",
        "skipPre": False,
        "targets": [
            {
                "group_name": "req",
                "limit": 1,
                "courses": ["10001"],
            }
        ],
    }


def _course(
    cid: str = "c1",
    no: str = "10001",
    code: str = "CODE1",
    week_state: int = 1,
    week_day: int = 1,
    start_unit: int = 1,
    end_unit: int = 2,
) -> dict:
    return {
        "id": cid,
        "no": no,
        "name": "course",
        "code": code,
        "arrangement": [(week_state, week_day, start_unit, end_unit)],
    }


class _FakeResponse:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, get_responses=None, post_responses=None) -> None:
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])

    def get(self, *args, **kwargs):
        if not self.get_responses:
            raise AssertionError("No fake GET response prepared")
        return self.get_responses.pop(0)

    def post(self, *args, **kwargs):
        if not self.post_responses:
            raise AssertionError("No fake POST response prepared")
        return self.post_responses.pop(0)


def _create_user(config: dict | None = None):
    atc.set_config_meta(
        {
            "domain": "classes.tju.edu.cn",
            "profileId": 1,
            "semesterId": 2,
            "startTime": "1970-01-01T08:00:00",
            "skipPre": False,
        }
    )
    return atc.create_user(config or _base_user_config())


def test_headers_cookie_loaded_from_user_config():
    user = _create_user()
    assert user.config.headers["Cookie"] == "cookie=test"


def test_skip_pre_explicit_false_is_preserved():
    cfg = _base_user_config()
    cfg["skipPre"] = False
    user = _create_user(cfg)
    assert user.config.skipPre is False


def test_query_courses_info_parse_success(monkeypatch):
    user = _create_user()
    fake_text = (
        "prefix "
        "[{'id':1,'no':'10001','name':'线代','code':'MATH001',"
        "'arrangeInfo':[{'weekState':'11','weekDay':1,'startUnit':1,'endUnit':2}]}]"
        " suffix"
    )

    class _DummySession:
        def __init__(self, *args, **kwargs): ...
        async def __aenter__(self):
            return _FakeSession(get_responses=[_FakeResponse(200, fake_text)])

        async def __aexit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr(aiohttp, "ClientSession", _DummySession)
    user.session = _FakeSession(get_responses=[_FakeResponse(200, fake_text)])  # type: ignore

    courses = asyncio.run(user.query_info())
    assert len(courses) == 1
    assert courses[0]["no"] == "10001"
    assert courses[0]["arrangement"] == [(3, 1, 1, 2)]


def test_query_status_parse_success_sets_course_status(monkeypatch):
    user = _create_user()
    user.config.set_course_status({})
    status_text = "anything {'1':{sc:1,lc:2,unplan:'否'}} anything"

    class _DummySession:
        def __init__(self, *args, **kwargs): ...
        async def __aenter__(self):
            return _FakeSession(get_responses=[_FakeResponse(200, status_text)])

        async def __aexit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr(aiohttp, "ClientSession", _DummySession)
    user.session = _FakeSession(get_responses=[_FakeResponse(200, status_text)])  # type: ignore
    asyncio.run(user.query_status())
    assert user.config.course_status["1"]["sc"] == 1
    assert user.config.course_status["1"]["lc"] == 2


def test_scheduler_check_conflict_when_course_full():
    user = _create_user()
    course = _course()
    user.config.set_courses_info([course])
    user.scheduler = user.Scheduler(user)
    user.config.set_course_status({"c1": {"sc": 10, "lc": 10}})

    assert user.scheduler.check_conflict(course) is True


def test_scheduler_check_conflict_when_no_conflict():
    user = _create_user()
    course = _course()
    user.config.set_courses_info([course])
    user.scheduler = user.Scheduler(user)
    user.config.set_course_status({"c1": {"sc": 1, "lc": 10}})
    assert user.scheduler.check_conflict(course) is False


def test_start_runs_scheduler_and_grab(monkeypatch):
    user = _create_user()
    user.config.set_course_status({"c1": {"sc": 1, "lc": 10}})

    async def fake_prepare():
        user.config.set_courses_info([_course()])
        user.scheduler = user.Scheduler(user)

    async def fake_query_status():
        return None

    called = {"grab": 0}

    async def fake_grab(course):
        called["grab"] += 1
        assert course["id"] == "c1"
        return True

    monkeypatch.setattr(user, "prepare", fake_prepare)
    monkeypatch.setattr(user, "query_status", fake_query_status)
    monkeypatch.setattr(user, "grab", fake_grab)
    monkeypatch.setattr(user.config, "startTime", 0.0)

    class _DummyClientSession:
        def __init__(self, *args, **kwargs): ...
        async def close(self): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(aiohttp, "ClientSession", _DummyClientSession)

    asyncio.run(user.start())

    assert called["grab"] == 1


def test_config_is_isolated_between_users():
    atc.set_config_meta(
        {
            "domain": "classes.tju.edu.cn",
            "profileId": 100,
            "semesterId": 200,
            "startTime": "1970-01-01T08:00:00",
            "skipPre": False,
        }
    )
    user_a = atc.create_user(
        {
            "name": "a",
            "cookie": "cookie=a",
            "targets": [{"group_name": "req", "limit": 1, "courses": ["10001"]}],
        }
    )
    user_b = atc.create_user(
        {
            "name": "b",
            "cookie": "cookie=b",
            "profileId": 999,
            "semesterId": 888,
            "domain": "custom.domain",
            "startTime": "1970-01-01T09:00:00",
            "skipPre": True,
            "targets": [{"group_name": "req", "limit": 1, "courses": ["10001"]}],
        }
    )

    assert user_a.config.profileId == 100
    assert user_a.config.domain == "classes.tju.edu.cn"
    assert user_a.config.skipPre is False
    assert user_b.config.profileId == 999
    assert user_b.config.domain == "custom.domain"
    assert user_b.config.skipPre is True


def test_set_config_meta_rejects_invalid_time_format():
    with pytest.raises(ValueError):
        atc.set_config_meta(
            {
                "domain": "classes.tju.edu.cn",
                "profileId": 1,
                "semesterId": 2,
                "startTime": "1970/01/01 08:00:00",
                "skipPre": False,
            }
        )


def test_create_user_rejects_missing_required_fields():
    atc.set_config_meta(
        {
            "domain": "classes.tju.edu.cn",
            "profileId": 1,
            "semesterId": 2,
            "startTime": "1970-01-01T08:00:00",
            "skipPre": False,
        }
    )
    with pytest.raises(ValueError):
        atc.create_user(
            {
                "name": "tester",
                "cookie": "cookie=test",
                "targets": [{"group_name": "req", "limit": 1}],  # missing courses
            }
        )
