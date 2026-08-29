import json
import os
import time
from collections.abc import Generator
from types import TracebackType

from loguru import logger

from .eams import (
    AuthenticationError,
    EamsClient,
    ProtocolError,
    SelectionState,
    SyncSession,
    TransportError,
)
from .logging import init_logger
from .models import UserConfig


class Session:
    """Own one authenticated HTTP session for one user run."""

    def __init__(
        self,
        headers: dict,
        *,
        domain: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.headers = headers
        self.domain = domain
        self.username = username
        self.password = password
        self.session: SyncSession | None = None
        self._depth = 0

    def __enter__(self) -> SyncSession:
        if self.session is not None:
            self._depth += 1
            return self.session
        self.session = SyncSession(headers=self.headers)
        self._depth = 1
        if self.username and self.password and self.domain:
            from .auth import login

            try:
                login(self.session, self.domain, self.username, self.password)
            except BaseException:
                self.session.close()
                self.session = None
                self._depth = 0
                raise
        return self.session

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        self._depth -= 1
        if self._depth == 0:
            self.session.close()
            self.session = None

    def reauthenticate(self) -> SyncSession:
        if not (self.domain and self.username and self.password):
            raise AuthenticationError(
                "cannot reauthenticate without username/password credentials"
            )
        old_session = self.session
        if old_session is not None:
            old_session.close()
        new_session = SyncSession(headers=self.headers)
        try:
            from .auth import login

            login(new_session, self.domain, self.username, self.password)
        except BaseException:
            new_session.close()
            self.session = None
            raise
        self.session = new_session
        return new_session


class RequestLimiter:
    """Space one user's requests using a monotonic clock."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last_request = time.monotonic()

    def wait(self) -> None:
        now = time.monotonic()
        time.sleep(max(0.0, self.interval + self._last_request - now))
        self._last_request = time.monotonic()


class Scheduler:
    """Turn a user's configured targets into ordered selection attempts."""

    def __init__(self, user: "User") -> None:
        self.user = user
        self.task_queue = []
        for target in user.config.targets:
            candidate_courses = [
                course
                for course_no in target.courses
                for course in self.user.courses_info
                if course_no == course["no"]
            ]
            self.task_queue.append(
                {
                    "group_name": target.group_name,
                    "target_count": target.limit,
                    "succeeded_count": 0,
                    "candidate_courses": candidate_courses,
                }
            )

    def begin(self) -> Generator[dict, bool | None]:
        yield {}
        for task in self.task_queue:
            group_name = task["group_name"]
            for course in task["candidate_courses"]:
                if task["succeeded_count"] >= task["target_count"] >= 0:
                    logger.info(
                        f"{self.user.name} [{group_name}] selected course limit reached"
                    )
                    break
                if self.check_conflict(course):
                    continue
                is_success = yield course
                if is_success is None:
                    logger.error(
                        f"{self.user.name} [{group_name}] selection result unknown; stopping scheduler"
                    )
                    return
                if is_success:
                    self.user.done.append(course)
                    task["succeeded_count"] += 1

    def check_conflict(self, course: dict) -> bool:
        if not self.user.config.skipPre:
            status: dict | None = self.course_status.get(course["id"])
            if status is None:
                logger.warning(
                    f"{self.user.name} course status unavailable: {course['name']}({course['no']})"
                )
                return True
            if status["sc"] >= status["lc"]:
                logger.warning(
                    f"{self.user.name} course is full: {course['name']}({course['no']})"
                )
                return True
        for selected_course in self.user.done:
            if selected_course["code"] == course["code"]:
                logger.warning(
                    f"{self.user.name} duplicate course code: {course['name']}({course['no']})"
                )
                return True
            for selected_time in selected_course["arrangement"]:
                for course_time in course["arrangement"]:
                    if (
                        selected_time[0] & course_time[0]
                        and selected_time[1] == course_time[1]
                        and max(selected_time[2], course_time[2])
                        <= min(selected_time[3], course_time[3])
                    ):
                        logger.warning(
                            f"{self.user.name} course time conflict: {course['name']}({course['no']})"
                        )
                        return True
        return False

    @property
    def course_status(self) -> dict:
        return self.user.course_status


class User:
    def __init__(self, config: dict) -> None:
        init_logger()
        self.name = config["name"]
        logger.info(f"{self.name} 初始化")
        self.config = UserConfig.model_validate(config)
        self.courses_info: list = []
        self.course_status: dict = {}
        self.done: list[dict] = []
        self.scheduler: Scheduler | None = None
        self.session = Session(
            headers=self.config.headers,
            domain=self.config.domain,
            username=self.config.username,
            password=self.config.password,
        )
        self.limiter = RequestLimiter(self.config.request_interval)
        logger.success(f"{self.name} 初始化成功")

    def run(self) -> None:
        with self.session:
            self.prepare()
            if self.scheduler is None:
                logger.error(f"{self.name} 调度器初始化失败")
                return
            start_time = self.config.startTime.timestamp()
            while time.time() < start_time:
                time.sleep(0.01)
            logger.info(f"{self.name} 开始选课")
            scheduler = self.scheduler.begin()
            result = False
            next(scheduler)
            while True:
                try:
                    course = scheduler.send(result)
                except StopIteration:
                    return
                result = self.fetch(course)
                if result is None:
                    if self.confirm_selection(course):
                        result = True
                    else:
                        logger.warning(
                            f"{self.name} 无法确认选课结果，本轮停止: {course['name']}({course['no']})"
                        )
                        return

    def prepare(self, save_path: str | None = None) -> None:
        with self.session as session:
            self.courses_info = self.query_info(session)
            if not self.course_status:
                self.course_status = self.query_status(session)
            if save_path is not None:
                os.makedirs(save_path, exist_ok=True)
                with open(
                    os.path.join(save_path, f"course_info_{self.name}.json"),
                    "w",
                    encoding="utf-8",
                ) as file:
                    json.dump(self.courses_info, file, ensure_ascii=False, indent=4)
                with open(
                    os.path.join(save_path, f"course_statu_{self.name}.json"),
                    "w",
                    encoding="utf-8",
                ) as file:
                    json.dump(self.course_status, file, ensure_ascii=False, indent=4)
                logger.success(f"{self.name} 课程信息与状态已保存到 {save_path}")
            self.done = self.query_done(session)
            self.scheduler = Scheduler(self)

    def wait(self, min_delay: float) -> None:
        if min_delay == self.config.request_interval:
            self.limiter.wait()
            return
        RequestLimiter(min_delay).wait()

    def _client(self, session) -> EamsClient:
        return EamsClient(
            session,
            domain=self.config.domain,
            profile_id=self.config.profileId,
            semester_id=self.config.semesterId,
        )

    def _call_with_auth_retry(self, operation, session=None):
        current_session = session or self.session.session
        remaining_retries = self.config.auth_retries
        while True:
            try:
                return operation(current_session)
            except AuthenticationError:
                if remaining_retries <= 0:
                    raise
                while remaining_retries > 0:
                    attempt = self.config.auth_retries - remaining_retries + 1
                    logger.warning(
                        f"{self.name} 会话失效，正在重新登录 ({attempt}/{self.config.auth_retries})"
                    )
                    remaining_retries -= 1
                    try:
                        current_session = self.session.reauthenticate()
                    except AuthenticationError:
                        if remaining_retries <= 0:
                            raise
                        continue
                    break

    def fetch(self, course: dict, session=None) -> bool | None:
        cid, cno, cname = course["id"], course["no"], course["name"]
        logger.info(f"{self.name} 尝试选课: {cname}({cno})")
        for attempt in range(self.config.too_fast_retries + 1):
            self.wait(self.config.request_interval)
            try:
                result = self._call_with_auth_retry(
                    lambda active_session: self._client(active_session).select_course(
                        cid
                    ),
                    session,
                )
            except TransportError:
                logger.error(f"{self.name} 请求超时，选课结果未知: {cname}({cno})")
                return None
            except ProtocolError:
                logger.error(f"{self.name} 请求失败: {cname}({cno})")
                return False
            if result.state is SelectionState.UNKNOWN:
                logger.warning(f"{self.name} 选课返回未知结果: {cname}({cno})")
                return None
            if result.state is SelectionState.SUCCESS:
                logger.success(f"{self.name} 选课成功: {cname}({cno})")
                return True
            if result.state is not SelectionState.TOO_FAST:
                messages = {
                    SelectionState.NOT_OPEN: "选课不开放",
                    SelectionState.FULL: "选课已满",
                    SelectionState.ALREADY_SELECTED: "选课已选过",
                }
                logger.warning(f"{self.name} {messages[result.state]}: {cname}({cno})")
                return False
            logger.warning(f"{self.name} 点击过快: {cname}({cno})")
        return False

    def confirm_selection(self, course: dict, session=None) -> bool:
        try:
            selected = self.query_done(session)
        except AuthenticationError:
            raise
        except (TransportError, ProtocolError) as exc:
            logger.error(f"{self.name} 确认选课结果失败: {exc}")
            return False
        return any(
            selected_course.get("id") == course.get("id")
            or selected_course.get("no") == course.get("no")
            for selected_course in selected
        )

    def query_info(self, session=None) -> list:
        logger.info(f"{self.name} 查询课程信息")
        self.wait(self.config.request_interval)
        try:
            result = self._call_with_auth_retry(
                lambda active_session: self._client(active_session).get_course_info(),
                session,
            )
        except AuthenticationError:
            logger.error(f"{self.name} 查询课程信息失败: 会话已失效")
            raise
        except (TransportError, ProtocolError) as exc:
            logger.error(f"{self.name} 查询课程信息失败: {exc}")
            raise
        logger.success(f"{self.name} 查询课程信息成功")
        return result

    def query_status(self, session=None) -> dict:
        logger.info(f"{self.name} 查询选课状态")
        self.wait(self.config.request_interval)
        try:
            result = self._call_with_auth_retry(
                lambda active_session: self._client(active_session).get_course_status(),
                session,
            )
        except AuthenticationError:
            logger.error(f"{self.name} 查询选课状态失败: 会话已失效")
            raise
        except (TransportError, ProtocolError) as exc:
            logger.error(f"{self.name} 查询选课状态失败: {exc}")
            raise
        logger.success(f"{self.name} 查询选课状态成功")
        return result

    def query_done(self, session=None) -> list[dict]:
        logger.info(f"{self.name} 查询已选课程")
        self.wait(self.config.request_interval)
        try:
            result = self._call_with_auth_retry(
                lambda active_session: self._client(
                    active_session
                ).get_selected_courses(self.courses_info),
                session,
            )
        except AuthenticationError:
            logger.error(f"{self.name} 查询已选课程失败: 会话已失效")
            raise
        except (TransportError, ProtocolError) as exc:
            logger.error(f"{self.name} 查询已选课程失败: {exc}")
            raise
        logger.success(f"{self.name} 查询已选课程成功")
        return result
