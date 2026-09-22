"""Typed EAMS operations; no scheduler or business retry policy here."""

from .auth import looks_like_login
from .domain import Capacity, Course, SelectionResult
from .errors import AuthenticationError, ProtocolError, TransportError
from .parsers import (
    parse_courses_text,
    parse_done_text,
    parse_ids_text,
    parse_name,
    parse_profiles,
    parse_selection,
    parse_status_text,
)


class EamsClient:
    def __init__(self, session, *, domain: str, profile_id: int, semester_id: int):
        self.session = session
        self.base_url = f"https://{domain}"
        self.profile_id = profile_id
        self.semester_id = semester_id

    def _request(self, method: str, path: str, **kwargs) -> str:
        response = self.session.request(method, self.base_url + path, **kwargs)
        if response.status >= 500:
            raise ProtocolError(f"EAMS 返回 HTTP {response.status}")
        location = response.headers.get("Location", "").lower()
        if (
            (300 <= response.status < 400 and "login" in location)
            or response.status in {401, 403}
            or looks_like_login(response.text)
        ):
            raise AuthenticationError("EAMS 会话已失效")
        if response.status != 200:
            raise ProtocolError(f"EAMS 返回 HTTP {response.status}")
        return response.text

    def verify_authenticated(self) -> None:
        text = self._request("GET", "/eams/homeExt.action", timeout=3)
        parse_name(text)

    def activate_profile(self) -> None:
        self._request(
            "POST",
            "/eams/stdElectCourse!defaultPage.action",
            data={"electionProfile.id": self.profile_id},
            timeout=3,
        )

    def get_course_info(self) -> list[Course]:
        return parse_courses_text(
            self._request(
                "GET",
                "/eams/stdElectCourse!data.action",
                params={"profileId": self.profile_id},
                timeout=3,
            )
        )

    def get_course_status(self) -> dict[str, Capacity]:
        return parse_status_text(
            self._request(
                "GET",
                "/eams/stdElectCourse!queryStdCount.action",
                params={"projectId": 1, "semesterId": self.semester_id},
                timeout=2,
            )
        )

    def get_selected_courses(self, courses: list[Course]) -> list[Course]:
        ids = parse_ids_text(
            self._request("GET", "/eams/courseTableForStd.action", timeout=2)
        )
        text = self._request(
            "POST",
            "/eams/courseTableForStd!courseTable.action",
            data={
                "ignoreHead": "1",
                "setting.kind": "std",
                "startWeek": "",
                "semester.id": self.semester_id,
                "ids": ids,
            },
            timeout=2,
        )
        numbers = set(parse_done_text(text))
        return [course for course in courses if course.no in numbers]

    def select_course(self, course_id: str) -> SelectionResult:
        try:
            text = self._request(
                "POST",
                "/eams/stdElectCourse!batchOperator.action",
                params={"profileId": self.profile_id},
                data={"optype": "true", "operator0": f"{course_id}:true:0"},
                timeout=2,
            )
        except (TransportError, ProtocolError):
            return SelectionResult.UNKNOWN
        return parse_selection(text)

    def get_name(self) -> str:
        return parse_name(self._request("GET", "/eams/homeExt.action", timeout=3))

    def get_semester_id(self) -> int:
        self._request("GET", "/eams/courseTableForStd.action", timeout=3)
        for cookie in self.session.cookies:
            if cookie.name == "semester.id" and cookie.value.isdigit():
                return int(cookie.value)
        raise ProtocolError("未找到 semesterId")

    def get_profiles(self) -> list[tuple[int, str]]:
        return parse_profiles(
            self._request("GET", "/eams/stdElectCourse.action", timeout=3)
        )
