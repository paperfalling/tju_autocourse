"""One user's lifecycle; HTTP and policy decisions live in dedicated modules."""

from datetime import datetime
from threading import Event

from .config import UserConfig
from .domain import Capacity, Course, SelectionResult
from .errors import Cancelled, ProtocolError, TransportError
from .scheduler import Scheduler, ScheduleReport
from .session import AuthenticatedEams
from .storage import save_snapshot
from .transport import Clock


class User:
    def __init__(self, config: UserConfig, *, client=None, clock=None):
        self.config = config
        self.name = config.name
        self.stop_event = Event()
        self.clock = clock or Clock(self.stop_event)
        self.client = (
            client
            if client is not None
            else AuthenticatedEams(config, clock=self.clock)
        )

    def cancel(self):
        self.stop_event.set()

    def _prepare(
        self, *, full_snapshot=False
    ) -> tuple[list[Course], dict[str, Capacity], list[Course]]:
        courses = self.client.get_course_info()
        if not courses:
            raise ProtocolError("课程列表为空，停止该用户")
        capacities = (
            self.client.get_course_status()
            if full_snapshot or not self.config.skipPre
            else {}
        )
        selected = self.client.get_selected_courses(courses)
        return courses, capacities, selected

    def _check_ready(self):
        if not self.config.profileId or not self.config.semesterId:
            raise ProtocolError("请先运行初始化工具填写 profileId 和 semesterId")

    def prepare(self, save_path=None):
        self._check_ready()
        with self.client:
            courses, capacities, selected = self._prepare(
                full_snapshot=save_path is not None
            )
            if save_path is not None:
                save_snapshot(save_path, self.name, courses, capacities)
            return courses, capacities, selected

    def run(self) -> ScheduleReport:
        self._check_ready()
        with self.client:
            courses, capacities, selected = self._prepare()
            # Naive datetimes deliberately retain the host's local timezone.
            target = self.config.startTime

            def remaining_time():
                if target.tzinfo is not None:
                    return target.timestamp() - self.clock.time()
                # Avoid Windows mktime failures around the default 1970 date.
                return (
                    target - datetime.fromtimestamp(self.clock.time())
                ).total_seconds()

            while (remaining := remaining_time()) > 0:
                self.clock.sleep(min(remaining, 0.1))
            scheduler = Scheduler(
                courses,
                capacities,
                selected,
                self.config.targets,
                skip_pre=self.config.skipPre,
                name=self.name,
            )
            return scheduler.run(self.fetch)

    def fetch(self, course: Course) -> SelectionResult:
        if self.stop_event.is_set():
            raise Cancelled("用户已中止")
        try:
            return self.client.select_course(course.id)
        except (TransportError, ProtocolError):
            # Unknown is deliberately NOT queried or counted as success.
            return SelectionResult.UNKNOWN
