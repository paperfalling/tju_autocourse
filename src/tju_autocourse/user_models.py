import asyncio
import time
from typing import Optional, Generator, TYPE_CHECKING

import aiohttp
from loguru import logger

from .parsers import parse_courses_text

if TYPE_CHECKING:
    from .user import User


class Config:
    def __init__(
        self,
        name: str,
        cookie: str,
        profileId: Optional[int] = None,
        semesterId: Optional[int] = None,
        domain: Optional[str] = None,
        startTime: Optional[str] = None,
        skipPre: Optional[bool] = None,
    ) -> None:
        self.cookie = cookie
        self.name = name
        self.__profileId = 0
        self.__semesterId = 0
        self.__domain = "classes.tju.edu.cn"
        self.__startTime = time.mktime(
            time.strptime("1970-01-01T08:00:00", "%Y-%m-%dT%H:%M:%S")
        )
        self.__skipPre = False
        self.__course_status: dict = {}
        if profileId is not None:
            self.__profileId = profileId
        if semesterId is not None:
            self.__semesterId = semesterId
        if domain is not None:
            self.__domain = domain
        if startTime is not None:
            self.__startTime = time.mktime(
                time.strptime(startTime, "%Y-%m-%dT%H:%M:%S")
            )
        if skipPre is not None:
            self.__skipPre = skipPre
        self.headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Content-Length": "39",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": self.domain,
            "Origin": f"http://{self.domain}",
            "Pragma": "no-cache",
            "x-requested-with": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": f"http://{self.domain}/eams/stdElectCourse!defaultPage.action",
            "Cookie": self.cookie,
        }
        self.courses_info = []

    async def query_courses_info(self, session: aiohttp.ClientSession) -> list:
        logger.info(f"{self.name} 查询课程信息")
        url = f"http://{self.domain}/eams/stdElectCourse!data.action?profileId={self.profileId}"
        try:
            async with session.get(
                url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                status_code = resp.status
                resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error(f"{self.name} 查询课程信息失败: Timeout")
            return []
        if status_code != 200:
            logger.error(f"{self.name} 查询课程信息失败: [{status_code}]")
            return []
        try:
            courses_info = parse_courses_text(resp_text)
        except ValueError as exc:
            logger.error(f"{self.name} 查询课程信息失败: {exc}")
            return []
        logger.success(f"{self.name} 查询课程信息成功")
        return courses_info

    @property
    def course_status(self) -> dict:
        return self.__course_status

    @property
    def profileId(self) -> int:
        return self.__profileId

    @property
    def semesterId(self) -> int:
        return self.__semesterId

    @property
    def domain(self) -> str:
        return self.__domain

    @property
    def startTime(self) -> float:
        return self.__startTime

    @property
    def skipPre(self) -> bool:
        return self.__skipPre

    def set_course_status(self, status: dict) -> None:
        self.__course_status = status


class Scheduler:
    def __init__(self, user: "User") -> None:
        self.user = user
        self.courses = {
            tag: [
                course
                for course_no in user.courses[tag]
                for course in self.user.config.courses_info
                if course_no == course["no"]
            ]
            for tag in user.courses
        }
        self.done = []

    def begin(self) -> Generator[dict, bool, None]:
        yield {}
        for tag in self.user.tsl:
            num = 0
            for course in self.courses[tag]:
                if num >= self.user.tsl[tag] >= 0:
                    logger.info(f"{self.user.name} {tag} 选课数量已达上限")
                    break
                if self.check_conflict(course):
                    continue
                if (yield course):
                    self.done.append(course)
                    num += 1
        return

    def check_conflict(self, course: dict) -> bool:
        if not self.user.config.skipPre:
            current_info: Optional[dict] = self.course_status.get(course["id"])
            if current_info is None:
                logger.warning(
                    f"{self.user.name} 未查询到课程状态: {course['name']}({course['no']})"
                )
                return True
            if current_info["sc"] >= current_info["lc"]:
                logger.warning(
                    f"{self.user.name} 选课已满: {course['name']}({course['no']})"
                )
                return True
        for dc in self.done:
            if dc["code"] == course["code"]:
                logger.warning(
                    f"{self.user.name} 已选过同课程代码课程: {course['name']}({course['no']})"
                )
                return True
            for i in dc["arrangement"]:
                for j in course["arrangement"]:
                    if (
                        i[0] & j[0]
                        and i[1] == j[1]
                        and max(i[2], j[2]) <= min(i[3], j[3])
                    ):
                        logger.warning(
                            f"{self.user.name} 课程时间冲突: {course['name']}({course['no']})"
                        )
                        return True
        return False

    @property
    def course_status(self) -> dict:
        return self.user.config.course_status
