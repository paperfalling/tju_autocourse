from email.message import Message
from types import SimpleNamespace

import pytest
import requests

from tju_autocourse.auth import CAS_URL, SsoAuthenticator
from tju_autocourse.config import SsoAuth
from tju_autocourse.domain import SelectionResult as R
from tju_autocourse.eams import EamsClient
from tju_autocourse.errors import AuthenticationError, ProtocolError, TransportError
from tju_autocourse.session import AuthenticatedEams
from tju_autocourse.transport import HttpSession, RequestLimiter

from .conftest import (
    COURSES,
    EMPTY_TABLE,
    HOME,
    TABLE_IDS,
    FakeClock,
    ScriptedHttp,
    response,
)


def client_for(raw, clock=None):
    transport = HttpSession(
        "classes.tju.edu.cn", RequestLimiter(clock or raw.clock), raw_session=raw
    )
    return EamsClient(
        transport, domain="classes.tju.edu.cn", profile_id=42, semester_id=134
    )


def test_every_actual_request_is_paced_even_on_transport_failure():
    clock = FakeClock()
    raw = ScriptedHttp(
        [
            response(TABLE_IDS),
            response(EMPTY_TABLE),
            requests.Timeout("sensitive URL"),
            response("成功"),
        ],
        clock,
    )
    client = client_for(raw, clock)
    assert client.get_selected_courses([]) == []
    assert client.select_course("1") is R.UNKNOWN
    assert client.select_course("2") is R.SUCCESS
    assert [call[0] for call in raw.calls] == pytest.approx([0, 0.55, 1.1, 1.65])
    assert raw.calls[1][3]["data"]["semester.id"] == 134
    assert raw.calls[2][3]["data"] == {"optype": "true", "operator0": "1:true:0"}


def test_cookie_is_scoped_updated_by_server_and_not_a_static_header():
    class Adapter(requests.adapters.BaseAdapter):
        def __init__(self):
            self.calls = []

        def send(self, request, **kwargs):
            self.calls.append(request)
            result = response("ok")
            result.request, result.url = request, request.url
            headers = Message()
            if len(self.calls) == 1:
                headers["Set-Cookie"] = "JSESSIONID=new; Path=/; Secure"
            result.raw = SimpleNamespace(
                _original_response=SimpleNamespace(msg=headers)
            )
            return result

        def close(self):
            pass

    raw = requests.Session()
    adapter = Adapter()
    raw.mount("https://", adapter)
    with HttpSession(
        "classes.tju.edu.cn", RequestLimiter(FakeClock()), raw_session=raw
    ) as session:
        session.import_cookie("JSESSIONID=old; semester.id=134")
        session.get("https://classes.tju.edu.cn/eams/homeExt.action")
        session.get("https://classes.tju.edu.cn/eams/data")
        session.get("https://learning.twt.edu.cn/enc")
        assert "JSESSIONID=old" in adapter.calls[0].headers["Cookie"]
        assert "JSESSIONID=new" in adapter.calls[1].headers["Cookie"]
        assert "old" not in adapter.calls[1].headers["Cookie"]
        assert "Cookie" not in adapter.calls[2].headers
        assert "Origin" not in adapter.calls[2].headers
        assert "Cookie" not in raw.headers


@pytest.mark.parametrize(
    "status,text,result",
    [
        (200, "选课成功", R.SUCCESS),
        (200, "点击过快", R.TOO_FAST),
        (200, "选课不开放", R.NOT_OPEN),
        (200, "选课未开始", R.NOT_OPEN),
        (200, "已满", R.FULL),
        (200, "已选过", R.ALREADY_SELECTED),
        (200, "陌生页面", R.UNKNOWN),
        (502, "成功", R.UNKNOWN),
    ],
)
def test_business_results(status, text, result):
    client = client_for(ScriptedHttp([response(text, status)]))
    assert client.select_course("1") is result


@pytest.mark.parametrize(
    "reply",
    [
        response("", 302, {"Location": CAS_URL}),
        response("", 302, {"location": CAS_URL}),
        response("", 401),
        response("", 403),
        response('<input id="username">'),
    ],
)
def test_auth_errors_do_not_become_unknown(reply):
    client = client_for(ScriptedHttp([reply]))
    with pytest.raises(AuthenticationError):
        client.select_course("1")


@pytest.mark.parametrize("reply", [response("garbage"), response("gateway", 502)])
def test_preparation_errors_are_not_empty_collections(reply):
    client = client_for(ScriptedHttp([reply]))
    with pytest.raises(ProtocolError):
        client.get_course_info()


def test_transport_errors_are_sanitized():
    session = client_for(
        ScriptedHttp([requests.ConnectionError("password=do-not-log")])
    ).session
    with pytest.raises(TransportError) as caught:
        session.get("https://classes.tju.edu.cn/test")
    assert "do-not-log" not in str(caught.value)


FORM = '<input type="hidden" name="lt" value="LT"><input type="hidden" name="execution" value="E1">'


def test_full_sso_login_uses_separate_helpers_and_validates_eams(make_config):
    clock = FakeClock()
    main = ScriptedHttp(
        [
            response(FORM),
            response(body=b"captcha"),
            response(
                "",
                302,
                {"location": "https://classes.tju.edu.cn/callback?ticket=dummy"},
            ),
            response(HOME),
            response(HOME),
            response("profile"),
            response(COURSES),
        ],
        clock,
    )
    helper = ScriptedHttp(
        [response('{"data":"encrypted"}'), response('{"data":"AB12"}')], clock
    )
    config = make_config(
        auth={"type": "sso", "username": "student", "password": "dummy-secret"}
    )
    owner = AuthenticatedEams(config, clock=clock)
    owner.session_factory = lambda: HttpSession(
        config.domain, owner.limiter, raw_session=main
    )
    owner.authenticator = SsoAuthenticator(
        config.auth,
        lambda: HttpSession(config.domain, owner.limiter, raw_session=helper),
    )
    with owner:
        assert owner.get_course_info()[0].no == "00001"
    assert main.closed and helper.closed
    assert len(helper.calls) == 2
    assert helper.calls[0][3]["data"]["val"] == "studentdummy-secretLT"
    assert helper.calls[1][3]["files"]["image"][1] == b"captcha"
    assert all("Origin" not in c[3].get("headers", {}) for c in helper.calls)
    assert main.calls[2][3]["data"]["code"] == "AB12"
    assert main.calls[5][3]["data"] == {"electionProfile.id": 1}
    starts = [call[0] for call in main.calls if "classes.tju.edu.cn" in call[2]]
    assert starts == pytest.approx([0, 0.55, 1.1, 1.65])


@pytest.mark.parametrize(
    "main_responses,helper_responses",
    [
        ([response("bad form")], []),
        ([response(FORM)], [response("not json")]),
        (
            [response(FORM), response(body=b"image")],
            [response('{"data":"RSA"}'), response('{"data":""}')],
        ),
        (
            [response(FORM), response(body=b"image"), response("invalid credentials")],
            [response('{"data":"RSA"}'), response('{"data":"1234"}')],
        ),
        ([requests.Timeout("secret")], []),
    ],
)
def test_sso_failure_paths(main_responses, helper_responses):
    clock = FakeClock()
    raw = ScriptedHttp(main_responses, clock)
    helper = ScriptedHttp(helper_responses, clock)
    session = HttpSession("classes.tju.edu.cn", RequestLimiter(clock), raw_session=raw)
    auth = SsoAuthenticator(
        SsoAuth(type="sso", username="u", password="p"),
        lambda: HttpSession(
            "classes.tju.edu.cn", RequestLimiter(clock), raw_session=helper
        ),
    )
    with session, pytest.raises(AuthenticationError):
        auth.authenticate(session, "classes.tju.edu.cn")
    assert raw.closed
    if helper.calls:
        assert helper.closed


@pytest.mark.parametrize(
    "replies",
    [
        [response("", 302)],
        [response("", 302, {"Location": "https://untrusted.invalid/path"})],
        [response("", 302, {"Location": "/next"})] * 6,
        [response("", 302, {"Location": "/next"}), response("fail", 500)],
    ],
)
def test_sso_rejects_invalid_redirects(replies):
    raw = ScriptedHttp(replies)
    auth = SsoAuthenticator(
        SsoAuth(type="sso", username="u", password="p"), lambda: None
    )
    with (
        HttpSession(
            "classes.tju.edu.cn", RequestLimiter(FakeClock()), raw_session=raw
        ) as session,
        pytest.raises(AuthenticationError),
    ):
        auth.authenticate(session, "classes.tju.edu.cn")


class StubAuthenticator:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = 0

    def authenticate(self, session, domain):
        self.calls += 1
        if self.calls <= self.failures:
            raise AuthenticationError("login failed")


def owner_with_scripts(config, scripts, authenticator=None):
    clock = FakeClock()
    raws = [ScriptedHttp(script, clock) for script in scripts]
    pending = iter(raws)
    owner = AuthenticatedEams(
        config, clock=clock, authenticator=authenticator or StubAuthenticator()
    )
    owner.session_factory = lambda: HttpSession(
        config.domain, owner.limiter, raw_session=next(pending)
    )
    return owner, raws


def test_reauthentication_restores_profile_and_pacing_before_replaying(make_config):
    config = make_config(
        auth={"type": "sso", "username": "u", "password": "p", "retries": 2}
    )
    owner, raws = owner_with_scripts(
        config,
        [
            [response(HOME), response("profile"), response("", 401)],
            [response(HOME), response("profile"), response("成功")],
        ],
    )
    with owner:
        assert owner.select_course("7") is R.SUCCESS
    assert all(raw.closed for raw in raws)
    calls = [call for raw in raws for call in raw.calls]
    assert [c[0] for c in calls] == pytest.approx([0, 0.55, 1.1, 1.65, 2.2, 2.75])
    assert calls[4][3]["data"] == {"electionProfile.id": 1}
    assert calls[5][3]["data"]["operator0"] == "7:true:0"


def test_successful_login_does_not_reset_recovery_budget(make_config):
    config = make_config(
        auth={"type": "sso", "username": "u", "password": "p", "retries": 2}
    )
    owner, raws = owner_with_scripts(
        config,
        [[response(HOME), response("profile"), response("", 401)] for _ in range(3)],
    )
    with pytest.raises(AuthenticationError), owner:
        owner.select_course("1")
    assert owner.authenticator.calls == 3
    assert all(raw.closed for raw in raws)


@pytest.mark.parametrize(
    "retries,failures,success", [(2, 2, True), (2, 3, False), (0, 1, False)]
)
def test_initial_login_budget_and_cleanup(make_config, retries, failures, success):
    config = make_config(
        auth={"type": "sso", "username": "u", "password": "p", "retries": retries}
    )
    auth = StubAuthenticator(failures)
    scripts = [[] for _ in range(min(failures, retries + 1))]
    if success:
        scripts.append([response(HOME), response("profile")])
    owner, raws = owner_with_scripts(config, scripts, auth)
    if success:
        with owner:
            pass
    else:
        with pytest.raises(AuthenticationError):
            owner.__enter__()
    assert auth.calls == retries + 1
    assert all(raw.closed for raw in raws)


def test_cookie_expiry_never_reauthenticates(make_config):
    owner, raws = owner_with_scripts(
        make_config(), [[response(HOME), response("profile"), response("", 401)]]
    )
    with pytest.raises(AuthenticationError), owner:
        owner.get_course_info()
    assert owner.authenticator.calls == 1 and raws[0].closed


def test_business_retry_budget_survives_real_auth_recovery(make_config):
    from tju_autocourse.user import User

    config = make_config(
        skipPre=True,
        auth={"type": "sso", "username": "u", "password": "p", "retries": 1},
        selection_policy={"full": {"action": "retry", "max_retries": 1}},
    )
    courses = COURSES.replace(
        "}];", "},{id:2,no:'00002',name:'英语',code:'ENG',arrangeInfo:[]}];"
    )
    owner, raws = owner_with_scripts(
        config,
        [
            [
                response(HOME),
                response("profile"),
                response(courses),
                response(TABLE_IDS),
                response(EMPTY_TABLE),
                response("已满"),
                response("", 401),
            ],
            [
                response(HOME),
                response("profile"),
                response("过快"),
                response("已满"),
                response("成功"),
            ],
        ],
    )
    report = User(config, client=owner, clock=owner.limiter.clock).run()
    assert [c.no for c in report.succeeded] == ["00002"]
    assert owner.authenticator.calls == 2
    assert all(raw.closed for raw in raws)
    posts = [
        c[3]["data"]["operator0"]
        for raw in raws
        for c in raw.calls
        if "batchOperator" in c[2]
    ]
    assert posts == ["1:true:0"] * 4 + ["2:true:0"]


def test_failure_text_containing_success_is_not_counted():
    client = client_for(
        ScriptedHttp(
            [
                response("选课未成功"),
                response("", 302, {"Location": "/eams/result.action"}),
                response("<a href='/cas/login'>gateway</a>", 502),
            ]
        )
    )
    assert client.select_course("1") is R.UNKNOWN
    assert client.select_course("1") is R.UNKNOWN
    assert client.select_course("1") is R.UNKNOWN
