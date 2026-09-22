"""HTTP ownership and per-user request pacing, including composite operations."""

from __future__ import annotations

import time as time_module
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlparse

import requests
from requests.structures import CaseInsensitiveDict

from .errors import AuthenticationError, Cancelled, TransportError

REQUEST_INTERVAL = 0.55


class Clock:
    monotonic = staticmethod(time_module.monotonic)
    time = staticmethod(time_module.time)

    def __init__(self, stop_event=None):
        self.stop_event = stop_event

    def sleep(self, seconds):
        if self.stop_event is None:
            time_module.sleep(seconds)
        elif self.stop_event.wait(seconds):
            raise Cancelled("用户已中止")


class RequestLimiter:
    def __init__(self, clock=None):
        self.clock = clock or Clock()
        self.last_start: float | None = None

    def wait(self):
        if self.last_start is not None:
            while (
                remaining := REQUEST_INTERVAL
                - (self.clock.monotonic() - self.last_start)
            ) > 1e-9:
                self.clock.sleep(remaining)
        self.last_start = self.clock.monotonic()


@dataclass(frozen=True)
class Response:
    status: int
    text: str = field(default="", repr=False)
    body: bytes = field(default=b"", repr=False)
    headers: Mapping[str, str] = field(default_factory=CaseInsensitiveDict, repr=False)


class HttpSession:
    def __init__(self, domain: str, limiter: RequestLimiter, *, raw_session=None):
        self.domain = domain
        self.limiter = limiter
        self.raw = raw_session if raw_session is not None else requests.Session()
        self.closed = False
        self.raw.headers.update(
            {
                "User-Agent": "Mozilla/5.0 TJU-AutoCourse",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )

    @property
    def cookies(self):
        return self.raw.cookies

    def import_cookie(self, value: str):
        parsed = SimpleCookie()
        try:
            parsed.load(value)
        except CookieError:
            raise AuthenticationError("Cookie 格式无法解析") from None
        if not parsed:
            raise AuthenticationError("Cookie 为空或格式无法解析")
        for name, cookie in parsed.items():
            self.raw.cookies.set(
                name, cookie.value, domain=self.domain, path="/", secure=True
            )

    def request(self, method: str, url: str, **kwargs) -> Response:
        if self.closed:
            raise RuntimeError("HTTP session is closed")
        # Also allow cancellation between CAS/helper requests, which are not paced.
        self.limiter.clock.sleep(0)
        kwargs.setdefault("timeout", 10)
        kwargs["allow_redirects"] = False
        if urlparse(url).hostname == self.domain:
            headers = {
                "Origin": f"https://{self.domain}",
                "Referer": f"https://{self.domain}/eams/stdElectCourse!defaultPage.action",
                "X-Requested-With": "XMLHttpRequest",
            }
            headers.update(kwargs.pop("headers", {}))
            kwargs["headers"] = headers
            self.limiter.wait()
        try:
            result = self.raw.request(method, url, **kwargs)
            if "charset=" not in result.headers.get("Content-Type", "").lower():
                result.encoding = "utf-8"
            return Response(
                result.status_code,
                result.text,
                result.content,
                CaseInsensitiveDict(result.headers),
            )
        except requests.RequestException:
            raise TransportError("HTTP 请求失败或超时") from None

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        if not self.closed:
            self.raw.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
