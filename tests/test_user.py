import datetime

import pytest

import tju_autocourse as atc
from tju_autocourse.eams import (
    AuthenticationError,
    ProtocolError,
    SelectionResult,
    SelectionState,
    TransportError,
)
from tju_autocourse.user import RequestLimiter, Scheduler, Session


def _config() -> dict:
    return {
        "name": "tester",
        "cookie": "cookie=test",
        "profileId": 1,
        "semesterId": 2,
        "domain": "classes.tju.edu.cn",
        "startTime": "1970-01-01T08:00:00",
        "skipPre": False,
        "targets": [{"group_name": "required", "limit": 1, "courses": ["10001"]}],
    }


def _user(config: dict | None = None):
    atc.set_config_meta(
        {
            "domain": "classes.tju.edu.cn",
            "profileId": 1,
            "semesterId": 2,
            "startTime": "1970-01-01T08:00:00",
            "skipPre": False,
        }
    )
    return atc.create_user(config or _config())


def _course(cid="c1", no="10001", code="CODE1", arrangement=None):
    return {
        "id": cid,
        "no": no,
        "name": "course",
        "code": code,
        "arrangement": arrangement or [(1, 1, 1, 2)],
    }


def test_session_reuses_nested_client_and_closes_once(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.close_count = 0

        def close(self):
            self.close_count += 1

    client = FakeClient()
    monkeypatch.setattr("tju_autocourse.user.SyncSession", lambda **_kwargs: client)
    wrapper = Session(headers={})

    with wrapper as outer:
        with wrapper as inner:
            assert outer is inner is client
        assert client.close_count == 0
    assert client.close_count == 1


def test_session_uses_independent_clients(monkeypatch):
    clients = []

    class FakeClient:
        def __init__(self):
            clients.append(self)

        def close(self):
            pass

    monkeypatch.setattr(
        "tju_autocourse.user.SyncSession", lambda **_kwargs: FakeClient()
    )
    first = Session(headers={})
    second = Session(headers={})

    with first as first_client, second as second_client:
        assert first_client is not second_client
    assert len(clients) == 2


def test_session_reauthentication_replaces_client_and_closes_old(monkeypatch):
    clients = []
    login_calls = []

    class FakeClient:
        def __init__(self):
            self.closed = False
            clients.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        "tju_autocourse.user.SyncSession", lambda **_kwargs: FakeClient()
    )
    monkeypatch.setattr(
        "tju_autocourse.auth.login", lambda *args: login_calls.append(args)
    )
    wrapper = Session(
        headers={}, domain="classes.tju.edu.cn", username="student", password="secret"
    )

    with wrapper as old_client:
        new_client = wrapper.reauthenticate()

    assert new_client is not old_client
    assert old_client.closed is True
    assert new_client.closed is True
    assert len(clients) == 2
    assert len(login_calls) == 2


def test_session_closes_client_when_login_fails(monkeypatch):
    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr("tju_autocourse.user.SyncSession", lambda **_kwargs: client)
    monkeypatch.setattr(
        "tju_autocourse.auth.login",
        lambda *_args: (_ for _ in ()).throw(AuthenticationError("invalid")),
    )
    wrapper = Session(
        headers={}, domain="classes.tju.edu.cn", username="student", password="secret"
    )

    with pytest.raises(AuthenticationError):
        wrapper.__enter__()
    assert client.closed is True
    assert wrapper.session is None


def test_scheduler_preserves_group_and_course_order():
    cfg = _config()
    cfg["targets"] = [
        {"group_name": "first", "limit": -1, "courses": ["10002", "10001"]},
        {"group_name": "second", "limit": 1, "courses": ["10003"]},
    ]
    user = _user(cfg)
    user.courses_info = [
        _course(no="10001"),
        _course(cid="c2", no="10002"),
        _course(cid="c3", no="10003"),
    ]
    user.course_status = {
        course["id"]: {"sc": 0, "lc": 1} for course in user.courses_info
    }
    generator = Scheduler(user).begin()
    next(generator)

    assert generator.send(False)["no"] == "10002"
    assert generator.send(False)["no"] == "10001"
    assert generator.send(False)["no"] == "10003"


def test_scheduler_limit_zero_skips_group():
    cfg = _config()
    cfg["targets"][0]["limit"] = 0
    user = _user(cfg)
    user.courses_info = [_course()]
    user.course_status = {"c1": {"sc": 0, "lc": 1}}
    generator = Scheduler(user).begin()
    next(generator)
    with pytest.raises(StopIteration):
        generator.send(False)


def test_scheduler_unknown_result_stops_before_next_course():
    cfg = _config()
    cfg["targets"][0]["courses"] = ["10001", "10002"]
    user = _user(cfg)
    user.courses_info = [_course(), _course(cid="c2", no="10002")]
    user.course_status = {"c1": {"sc": 0, "lc": 1}, "c2": {"sc": 0, "lc": 1}}
    generator = Scheduler(user).begin()
    next(generator)
    assert generator.send(False)["no"] == "10001"
    with pytest.raises(StopIteration):
        generator.send(None)


@pytest.mark.parametrize(
    "state,expected",
    [
        (SelectionState.SUCCESS, True),
        (SelectionState.FULL, False),
        (SelectionState.ALREADY_SELECTED, False),
        (SelectionState.TOO_FAST, False),
        (SelectionState.NOT_OPEN, False),
    ],
)
def test_fetch_maps_business_results(monkeypatch, state, expected):
    user = _user()

    class FakeClient:
        def select_course(self, _course_id):
            return SelectionResult(state)

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    assert user.fetch(_course()) is expected


def test_fetch_retries_too_fast_with_configured_interval(monkeypatch):
    cfg = _config()
    cfg["too_fast_retries"] = 2
    user = _user(cfg)
    responses = iter(
        [
            SelectionResult(SelectionState.TOO_FAST),
            SelectionResult(SelectionState.TOO_FAST),
            SelectionResult(SelectionState.SUCCESS),
        ]
    )
    delays = []

    class FakeClient:
        def select_course(self, _course_id):
            return next(responses)

    monkeypatch.setattr(user, "wait", delays.append)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    assert user.fetch(_course()) is True
    assert delays == [user.config.request_interval] * 3


def test_fetch_stops_after_too_fast_retry_budget(monkeypatch):
    cfg = _config()
    cfg["too_fast_retries"] = 1
    user = _user(cfg)
    delays = []

    class FakeClient:
        def select_course(self, _course_id):
            return SelectionResult(SelectionState.TOO_FAST)

    monkeypatch.setattr(user, "wait", delays.append)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    assert user.fetch(_course()) is False
    assert delays == [user.config.request_interval] * 2


def test_fetch_returns_unknown_for_transport_failure(monkeypatch):
    user = _user()

    class FakeClient:
        def select_course(self, _course_id):
            raise TransportError("timeout")

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    assert user.fetch(_course()) is None


def test_cookie_session_cannot_reauthenticate_after_expiry(monkeypatch):
    user = _user()

    class FakeClient:
        def select_course(self, _course_id):
            raise AuthenticationError("expired")

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    with pytest.raises(AuthenticationError, match="cannot reauthenticate"):
        user.fetch(_course())


def test_fetch_reauthenticates_and_retries_after_session_expiry(monkeypatch):
    cfg = _config()
    cfg.pop("cookie")
    cfg.update({"username": "student", "password": "secret", "auth_retries": 2})
    user = _user(cfg)
    clients = iter(
        [
            type(
                "FirstClient",
                (),
                {
                    "select_course": lambda _self, _id: (_ for _ in ()).throw(
                        AuthenticationError("expired")
                    )
                },
            )(),
            type(
                "SecondClient",
                (),
                {
                    "select_course": lambda _self, _id: SelectionResult(
                        SelectionState.SUCCESS
                    )
                },
            )(),
        ]
    )
    reauth_calls = []
    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: next(clients))
    monkeypatch.setattr(
        user.session,
        "reauthenticate",
        lambda: reauth_calls.append("reauthenticated") or object(),
    )

    assert user.fetch(_course()) is True
    assert reauth_calls == ["reauthenticated"]


def test_fetch_retries_when_reauthentication_itself_fails(monkeypatch):
    cfg = _config()
    cfg.pop("cookie")
    cfg.update({"username": "student", "password": "secret", "auth_retries": 2})
    user = _user(cfg)
    client_results = iter(
        [
            AuthenticationError("expired"),
            SelectionResult(SelectionState.SUCCESS),
        ]
    )
    reauth_results = iter([AuthenticationError("login failed"), object()])
    reauth_calls = []

    class FakeClient:
        def select_course(self, _course_id):
            result = next(client_results)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    def reauthenticate():
        reauth_calls.append("reauthenticated")
        result = next(reauth_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(user.session, "reauthenticate", reauthenticate)

    assert user.fetch(_course()) is True
    assert len(reauth_calls) == 2


def test_fetch_stops_after_authentication_retry_budget(monkeypatch):
    cfg = _config()
    cfg.pop("cookie")
    cfg.update({"username": "student", "password": "secret", "auth_retries": 2})
    user = _user(cfg)
    reauth_calls = []

    class FakeClient:
        def select_course(self, _course_id):
            raise AuthenticationError("expired")

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())
    monkeypatch.setattr(
        user.session,
        "reauthenticate",
        lambda: reauth_calls.append("reauthenticated") or object(),
    )

    with pytest.raises(AuthenticationError, match="expired"):
        user.fetch(_course())
    assert len(reauth_calls) == 2


def test_fetch_maps_protocol_failure_to_business_failure(monkeypatch):
    user = _user()

    class FakeClient:
        def select_course(self, _course_id):
            raise ProtocolError("bad response")

    monkeypatch.setattr(user, "wait", lambda _delay: None)
    monkeypatch.setattr(user, "_client", lambda _session: FakeClient())

    assert user.fetch(_course()) is False


def test_prepare_builds_scheduler_from_all_queries(monkeypatch):
    user = _user()
    courses = [_course()]
    status = {"c1": {"sc": 0, "lc": 1}}
    selected = [_course()]
    calls = []
    monkeypatch.setattr(
        user, "query_info", lambda _session: calls.append("info") or courses
    )
    monkeypatch.setattr(
        user, "query_status", lambda _session: calls.append("status") or status
    )
    monkeypatch.setattr(
        user, "query_done", lambda _session: calls.append("done") or selected
    )

    user.prepare()

    assert calls == ["info", "status", "done"]
    assert user.courses_info == courses
    assert user.course_status == status
    assert user.done == selected
    assert user.scheduler is not None


def test_run_calls_prepare_and_fetch_and_closes_session(monkeypatch):
    user = _user()
    course = _course()
    fetched = []

    def fake_prepare():
        user.courses_info = [course]
        user.course_status = {"c1": {"sc": 0, "lc": 1}}
        user.scheduler = Scheduler(user)

    monkeypatch.setattr(user, "prepare", fake_prepare)
    monkeypatch.setattr(user, "fetch", lambda value: fetched.append(value) or True)
    monkeypatch.setattr(
        user.config,
        "startTime",
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
    )

    user.run()

    assert fetched == [course]
    assert user.session.session is None


def test_request_limiter_spaces_consecutive_requests(monkeypatch):
    clock = iter([10.0, 10.0, 10.1, 10.2, 10.7, 10.7])
    sleeps = []
    monkeypatch.setattr("tju_autocourse.user.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("tju_autocourse.user.time.sleep", sleeps.append)
    limiter = RequestLimiter(0.5)

    limiter.wait()
    limiter.wait()

    assert sleeps == [pytest.approx(0.5), pytest.approx(0.4)]
