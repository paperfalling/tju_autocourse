"""Shared synchronous EAMS client and typed request results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import requests

from .parsers import (
    parse_courses_text,
    parse_done_text,
    parse_ids_text,
    parse_status_text,
)


class Response:
    def __init__(self, response: requests.Response) -> None:
        self.status = response.status_code
        self.headers = response.headers
        self.body = response.content
        self.text = response.text


class SyncSession:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._session = requests.Session()
        self._session.headers.update(headers or {})
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    @property
    def cookies(self):
        return self._session.cookies

    def close(self) -> None:
        if not self.closed:
            self._session.close()
            self.closed = True

    def request(self, method: str, url: str, **kwargs) -> Response:
        if self.closed:
            raise RuntimeError("HTTP session is closed")
        kwargs.setdefault("allow_redirects", False)
        try:
            response = self._session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise OSError("HTTP request failed") from exc
        return Response(response)

    def get(self, url: str, **kwargs) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Response:
        return self.request("POST", url, **kwargs)


class AuthenticationError(RuntimeError):
    """Raised when a CAS or EAMS session is no longer authenticated."""


class EamsError(RuntimeError):
    """Base class for EAMS request failures."""


class TransportError(EamsError):
    """The request could not reach EAMS or timed out."""


class ProtocolError(EamsError):
    """EAMS returned an unexpected status or response shape."""


class SelectionState(StrEnum):
    SUCCESS = "success"
    FULL = "full"
    ALREADY_SELECTED = "already_selected"
    TOO_FAST = "too_fast"
    NOT_OPEN = "not_open"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SelectionResult:
    state: SelectionState

    @property
    def succeeded(self) -> bool:
        return self.state is SelectionState.SUCCESS


class EamsClient:
    def __init__(
        self,
        session: SyncSession,
        *,
        domain: str,
        profile_id: int,
        semester_id: int,
    ) -> None:
        self.session = session
        self.base_url = f"https://{domain}"
        self.profile_id = profile_id
        self.semester_id = semester_id

    def _request(self, method: str, path: str, **kwargs) -> str:
        url = f"{self.base_url}{path}"
        try:
            response: Response = self.session.request(method, url, **kwargs)
        except (TimeoutError, OSError) as exc:
            raise TransportError("EAMS request failed") from exc
        text = response.text
        if (
            300 <= response.status < 400
            or response.status in {401, 403}
            or self._looks_like_login(text)
        ):
            raise AuthenticationError("EAMS session is not authenticated")
        if response.status != 200:
            raise ProtocolError(f"EAMS returned unexpected status {response.status}")
        return text

    @staticmethod
    def _looks_like_login(text: str) -> bool:
        lowered = text.lower()
        return "cas/login" in lowered or 'id="username"' in lowered

    def get_course_info(self) -> list[dict]:
        self._request(
            "POST",
            "/eams/stdElectCourse!defaultPage.action",
            data={"electionProfile.id": self.profile_id},
            timeout=3,
        )
        text = self._request(
            "GET",
            "/eams/stdElectCourse!data.action",
            params={"profileId": self.profile_id},
            timeout=3,
        )
        try:
            return parse_courses_text(text)
        except ValueError as exc:
            raise ProtocolError("invalid EAMS course information") from exc

    def get_course_status(self) -> dict:
        text = self._request(
            "GET",
            "/eams/stdElectCourse!queryStdCount.action",
            params={"projectId": 1, "semesterId": self.semester_id},
            timeout=2,
        )
        try:
            return parse_status_text(text)
        except ValueError as exc:
            raise ProtocolError("invalid EAMS course status") from exc

    def get_selected_courses(self, courses_info: list[dict]) -> list[dict]:
        ids_text = self._request("GET", "/eams/courseTableForStd.action", timeout=2)
        try:
            ids = parse_ids_text(ids_text)
        except ValueError as exc:
            raise ProtocolError("invalid EAMS selected-course identifiers") from exc
        table_text = self._request(
            "POST",
            "/eams/courseTableForStd!courseTable.action",
            data={
                "ignoreHead": "1",
                "setting.kind": "std",
                "startWeek": None,
                "semester.id": self.semester_id,
                "ids": ids,
            },
            timeout=2,
        )
        try:
            selected_numbers = parse_done_text(table_text)
        except (ValueError, TypeError) as exc:
            raise ProtocolError("invalid EAMS selected-course table") from exc
        return [
            course
            for course_no in selected_numbers
            for course in courses_info
            if course_no == course["no"]
        ]

    def select_course(self, course_id: str) -> SelectionResult:
        text = self._request(
            "POST",
            "/eams/stdElectCourse!batchOperator.action",
            params={"profileId": self.profile_id},
            data={"optype": "true", "operator0": f"{course_id}:true:0"},
            timeout=2,
        )
        if "成功" in text:
            state = SelectionState.SUCCESS
        elif "过快" in text:
            state = SelectionState.TOO_FAST
        elif "不开放" in text:
            state = SelectionState.NOT_OPEN
        elif "已满" in text:
            state = SelectionState.FULL
        elif "选过" in text:
            state = SelectionState.ALREADY_SELECTED
        else:
            state = SelectionState.UNKNOWN
        return SelectionResult(state)
