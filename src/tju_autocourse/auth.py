"""Cookie and TJU CAS authentication, without business retry decisions."""

import json
from urllib.parse import urljoin, urlparse

from lxml import etree, html

from .config import CookieAuth, SsoAuth
from .errors import AuthenticationError, TransportError

CAS_URL = "https://sso.tju.edu.cn/cas/login"
HELPER_URL = "https://learning.twt.edu.cn"


def looks_like_login(text: str) -> bool:
    lowered = text.lower()
    return (
        "cas/login" in lowered
        or 'id="username"' in lowered
        or "id='username'" in lowered
    )


def _hidden_fields(body: str) -> dict[str, str]:
    try:
        tree = html.fromstring(body)
    except (ValueError, etree.ParserError):
        raise AuthenticationError("SSO 登录表单无法解析") from None
    return {
        node.get("name"): node.get("value", "")
        for node in tree.xpath(
            '//input[@name][translate(@type,"HIDDEN","hidden")="hidden"]'
        )
    }


def _helper_value(response) -> str:
    if response.status != 200:
        raise AuthenticationError("SSO 辅助服务返回错误状态")
    try:
        value = json.loads(response.text)
    except (ValueError, TypeError):
        raise AuthenticationError("SSO 辅助服务返回无效数据") from None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("data"), str)
        or not value["data"].strip()
    ):
        raise AuthenticationError("SSO 辅助服务未返回有效结果")
    return value["data"]


def _follow_redirects(session, base: str, location: str | None, domain: str):
    for _ in range(5):
        if not location:
            raise AuthenticationError("SSO 跳转缺少 Location")
        target = urljoin(base, location)
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.hostname not in {
            "sso.tju.edu.cn",
            domain,
        }:
            raise AuthenticationError("SSO 返回非预期的跳转目标")
        response = session.get(target)
        if 300 <= response.status < 400:
            base, location = target, response.headers.get("Location")
            continue
        if response.status != 200 or looks_like_login(response.text):
            raise AuthenticationError("SSO 跳转未建立登录状态")
        return
    raise AuthenticationError("SSO 跳转超过 5 次")


class CookieAuthenticator:
    def __init__(self, config: CookieAuth):
        self.config = config

    def authenticate(self, session, domain: str):
        session.import_cookie(self.config.cookie.get_secret_value())


class SsoAuthenticator:
    def __init__(self, config: SsoAuth, helper_factory):
        self.config = config
        self.helper_factory = helper_factory

    def authenticate(self, session, domain: str):
        try:
            self._login(session, domain)
        except TransportError:
            raise AuthenticationError("SSO 登录服务不可达或请求超时") from None

    def _login(self, session, domain):
        service = {
            "service": f"https://{domain}/eams/stdElectCourse!defaultPage.action"
        }
        response = session.get(CAS_URL, params=service)
        if 300 <= response.status < 400:
            _follow_redirects(
                session, CAS_URL, response.headers.get("Location"), domain
            )
            return
        if response.status != 200:
            raise AuthenticationError("SSO 登录页返回错误状态")
        fields = _hidden_fields(response.text)
        if not fields.get("lt") or not fields.get("execution"):
            raise AuthenticationError("SSO 登录表单缺少 lt/execution")
        username = self.config.username.get_secret_value()
        password = self.config.password.get_secret_value()
        # Helpers intentionally use a separate cookie jar from CAS/EAMS.
        with self.helper_factory() as helper:
            rsa = _helper_value(
                helper.post(
                    f"{HELPER_URL}/enc",
                    data={"val": username + password + fields["lt"]},
                )
            )
            captcha = session.get("https://sso.tju.edu.cn/cas/code")
            if captcha.status != 200 or not captcha.body:
                raise AuthenticationError("无法获取 SSO 验证码")
            code = _helper_value(
                helper.post(
                    f"{HELPER_URL}/ocr",
                    files={"image": ("captcha.jpg", captcha.body, "image/jpeg")},
                )
            )
        payload = {
            "code": code,
            "ul": str(len(username)),
            "pl": str(len(password)),
            "lt": fields["lt"],
            "rsa": rsa,
            "execution": fields["execution"],
            "_eventId": "submit",
        }
        response = session.post(CAS_URL, params=service, data=payload)
        if 300 <= response.status < 400:
            _follow_redirects(
                session, CAS_URL, response.headers.get("Location"), domain
            )
        elif (
            response.status != 200 or "remind_strong_pwd = 'true'" not in response.text
        ):
            raise AuthenticationError("SSO 登录失败，请检查账号、密码或验证码")
        # The owner verifies the EAMS session even for the strong-password page.
