import pytest

from tju_autocourse.auth import AuthenticationError, _hidden_fields, login
from tju_autocourse.user import Session


class FakeResponse:
    def __init__(
        self, status=200, *, text="", body=b"captcha", headers=None, json_value=None
    ):
        import json

        self.status = status
        self.headers = headers or {}
        self.body = body
        self.text = json.dumps(json_value) if json_value is not None else text


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)

    get = lambda self, url, **kwargs: self.request("GET", url, **kwargs)
    post = lambda self, url, **kwargs: self.request("POST", url, **kwargs)


def _login_form():
    return '<input type="hidden" name="lt" value="LT-1"><input type="hidden" name="execution" value="e1">'


def test_login_completes_cas_helper_captcha_and_redirect_chain():
    session = FakeSession(
        [
            FakeResponse(text=_login_form()),
            FakeResponse(json_value={"data": "RSA-1"}),
            FakeResponse(body=b"image-bytes"),
            FakeResponse(json_value={"data": "AB12"}),
            FakeResponse(status=302, headers={"Location": "/eams/start"}),
            FakeResponse(
                status=302, headers={"Location": "https://classes.tju.edu.cn/home"}
            ),
            FakeResponse(status=200),
        ]
    )
    login(session, "classes.tju.edu.cn", "student", "secret")
    assert [call[:2] for call in session.calls] == [
        ("GET", "https://sso.tju.edu.cn/cas/login"),
        ("POST", "https://learning.twt.edu.cn/enc"),
        ("GET", "https://sso.tju.edu.cn/cas/code"),
        ("POST", "https://learning.twt.edu.cn/ocr"),
        ("POST", "https://sso.tju.edu.cn/cas/login"),
        ("GET", "https://sso.tju.edu.cn/eams/start"),
        ("GET", "https://classes.tju.edu.cn/home"),
    ]
    service_params = {
        "service": "https://classes.tju.edu.cn/eams/stdElectCourse!defaultPage.action"
    }
    assert session.calls[0][2]["params"] == service_params
    assert session.calls[4][2]["params"] == service_params


def test_login_accepts_existing_authenticated_cas_session():
    session = FakeSession(
        [
            FakeResponse(status=302, headers={"Location": "/eams/start"}),
            FakeResponse(status=200),
        ]
    )
    login(session, "classes.tju.edu.cn", "student", "secret")
    assert len(session.calls) == 2


def test_login_follows_standard_non_302_redirects():
    session = FakeSession(
        [
            FakeResponse(text=_login_form()),
            FakeResponse(json_value={"data": "RSA-1"}),
            FakeResponse(body=b"image"),
            FakeResponse(json_value={"data": "AB12"}),
            FakeResponse(status=303, headers={"Location": "/eams/start"}),
            FakeResponse(status=200),
        ]
    )
    login(session, "classes.tju.edu.cn", "student", "secret")


@pytest.mark.parametrize(
    "responses,message",
    [
        ([FakeResponse(text="<form></form>")], "missing execution/lt"),
        ([FakeResponse(text=_login_form()), FakeResponse(text="bad")], "invalid data"),
        (
            [
                FakeResponse(text=_login_form()),
                FakeResponse(json_value={"data": "RSA-1"}),
                FakeResponse(),
                FakeResponse(json_value={"data": ""}),
            ],
            "no code",
        ),
        (
            [
                FakeResponse(text=_login_form()),
                FakeResponse(json_value={"data": "RSA-1"}),
                FakeResponse(),
                FakeResponse(json_value={"data": "AB12"}),
                FakeResponse(text="login failed"),
            ],
            "invalid username",
        ),
        (
            [
                FakeResponse(text=_login_form()),
                FakeResponse(json_value={"data": "RSA-1"}),
                FakeResponse(),
                FakeResponse(json_value={"data": "AB12"}),
                FakeResponse(status=302, headers={"Location": "/eams/start"}),
                FakeResponse(status=500),
            ],
            "redirect",
        ),
    ],
)
def test_login_reports_failures(responses, message):
    with pytest.raises(AuthenticationError, match=message):
        login(FakeSession(responses), "classes.tju.edu.cn", "student", "secret")


def test_hidden_fields_are_extracted():
    assert _hidden_fields(_login_form()) == {"lt": "LT-1", "execution": "e1"}


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


def test_nested_session_reuses_authenticated_client(monkeypatch):
    class FakeClient:
        close_count = 0

        def close(self):
            self.close_count += 1

    client = FakeClient()
    calls = []
    monkeypatch.setattr("tju_autocourse.user.SyncSession", lambda **_kwargs: client)
    monkeypatch.setattr("tju_autocourse.auth.login", lambda *args: calls.append(args))
    wrapper = Session(
        headers={}, domain="classes.tju.edu.cn", username="student", password="secret"
    )
    with wrapper as outer:
        with wrapper as inner:
            assert inner is outer
            assert len(calls) == 1
        assert client.close_count == 0
    assert client.close_count == 1
