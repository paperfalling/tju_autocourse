import aiohttp
import datetime
from typing import Optional, Generator, TYPE_CHECKING
from pydantic import BaseModel, Field, PrivateAttr
from loguru import logger

if TYPE_CHECKING:
    from .user import User


class Config(BaseModel):
    name: str
    cookie: str
    profileId: int = 0
    semesterId: int = 0
    domain: str = "classes.tju.edu.cn"
    startTime: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.strptime(
            "1970-01-01T08:00:00", "%Y-%m-%dT%H:%M:%S"
        )
    )
    skipPre: bool = False

    _courses_info: list = PrivateAttr(default_factory=list)
    _course_status: dict = PrivateAttr(default_factory=dict)

    @property
    def headers(self) -> dict:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
            "Origin": f"https://{self.domain}",
            "x-requested-with": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": f"https://{self.domain}/eams/stdElectCourse!defaultPage.action",
            "Cookie": self.cookie,
        }

    @property
    def course_status(self) -> dict:
        return self._course_status

    def set_course_status(self, status: dict) -> None:
        self._course_status = status

    @property
    def courses_info(self) -> list:
        return self._courses_info

    def set_courses_info(self, info: list) -> None:
        self._courses_info = info


class Scheduler:
    def __init__(self, user: "User") -> None:
        self.user = user
        self.task_queue = []
        for target in user.targets:
            candidate_courses = [
                course
                for course_no in target["courses"]
                for course in self.user.config.courses_info
                if course_no == course["no"]
            ]
            self.task_queue.append(
                {
                    "group_name": target["group_name"],
                    "target_count": target["limit"],
                    "succeeded_count": 0,
                    "candidate_courses": candidate_courses,
                }
            )
        self.done = []

    def begin(self) -> Generator[dict, bool, None]:
        yield {}
        for task in self.task_queue:
            group_name = task["group_name"]
            for course in task["candidate_courses"]:
                if task["succeeded_count"] >= task["target_count"] >= 0:
                    logger.info(f"{self.user.name} [{group_name}] 选课数量已达上限")
                    break
                if self.check_conflict(course):
                    continue
                is_success = yield course
                if is_success:
                    self.done.append(course)
                    task["succeeded_count"] += 1
        return

    def check_conflict(self, course: dict) -> bool:
        if not self.user.config.skipPre:
            statu: Optional[dict] = self.course_status.get(course["id"])
            if statu is None:
                logger.warning(
                    f"{self.user.name} 未查询到课程状态: {course['name']}({course['no']})"
                )
                return True
            if statu["sc"] >= statu["lc"]:
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


class Session:
    def __init__(self, headers: dict) -> None:
        self.headers = headers
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(limit=1, keepalive_timeout=30)
        self.session = aiohttp.ClientSession(connector=connector, headers=self.headers)
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session is not None:
            await self.session.close()
