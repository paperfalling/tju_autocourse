import pytest
import requests

from tju_autocourse.config import parse_config
from tju_autocourse.domain import Course, Meeting


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedHttp:
    def __init__(self, responses, clock=None):
        self.responses = iter(responses)
        self.clock = clock or FakeClock()
        self.headers = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((self.clock.now, method, url, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        if callable(result):
            result = result(self, method, url, kwargs)
        return result

    def close(self):
        self.closed = True


def response(text="", status=200, headers=None, body=None):
    result = requests.Response()
    result.status_code = status
    result._content = text.encode() if body is None else body
    result.headers.update(headers or {})
    result.encoding = "utf-8"
    return result


HOME = '<div id="main-top"><div><div><div><a>测试用户</a></div></div></div></div>'
COURSES = "var courses=[{id:1,no:'00001',name:'数学',code:'MATH',arrangeInfo:[{weekState:'11',weekDay:1,startUnit:1,endUnit:2}]}];"
TABLE_IDS = 'bg.form.addInput(form,"ids","123");'
EMPTY_TABLE = '<tbody id="grid123_data"></tbody>'


@pytest.fixture
def make_config():
    def make(**overrides):
        user = {
            "name": "tester",
            "auth": {"type": "cookie", "cookie": "session=test"},
            "profileId": 1,
            "semesterId": 2,
            "targets": [{"group_name": "g", "limit": 1, "courses": ["00001", "00002"]}],
        } | overrides
        return parse_config({"users": [user]}).users[0]

    return make


@pytest.fixture
def course():
    def make(number="00001", *, code=None, day=1, weeks=3, start=1, end=2):
        return Course(
            str(int(number)),
            number,
            f"course {number}",
            code or number,
            (Meeting(weeks, day, start, end),),
        )

    return make
