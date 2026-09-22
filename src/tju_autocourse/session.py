"""One user owns one live authenticated session and a persistent limiter."""

from collections.abc import Callable

from loguru import logger

from .auth import CookieAuthenticator, SsoAuthenticator
from .config import SsoAuth, UserConfig
from .domain import Capacity, Course, SelectionResult
from .eams import EamsClient
from .errors import AuthenticationError, ProtocolError, TransportError
from .transport import HttpSession, RequestLimiter


class AuthenticatedEams:
    def __init__(
        self,
        config: UserConfig,
        *,
        clock=None,
        session_factory=None,
        helper_factory=None,
        authenticator=None,
    ):
        self.config = config
        self.limiter = RequestLimiter(clock)
        self.session_factory = session_factory or (
            lambda: HttpSession(config.domain, self.limiter)
        )
        helper_factory = helper_factory or (
            lambda: HttpSession(config.domain, self.limiter)
        )
        self.authenticator = authenticator or (
            SsoAuthenticator(config.auth, helper_factory)
            if isinstance(config.auth, SsoAuth)
            else CookieAuthenticator(config.auth)
        )
        self.session: HttpSession | None = None
        self.client: EamsClient | None = None

    def close(self):
        if self.session is not None:
            self.session.close()
        self.session = self.client = None

    def _establish(self):
        self.close()
        self.session = self.session_factory()
        try:
            self.authenticator.authenticate(self.session, self.config.domain)
            self.client = EamsClient(
                self.session,
                domain=self.config.domain,
                profile_id=self.config.profileId,
                semester_id=self.config.semesterId,
            )
            try:
                self.client.verify_authenticated()
                if self.config.profileId:
                    self.client.activate_profile()
            except (ProtocolError, TransportError):
                raise AuthenticationError(
                    "无法确认 EAMS 登录状态或恢复选课轮次"
                ) from None
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        attempts = 1 + (
            self.config.auth.retries if isinstance(self.config.auth, SsoAuth) else 0
        )
        for attempt in range(attempts):
            try:
                self._establish()
                return self
            except AuthenticationError:
                if attempt + 1 == attempts:
                    raise
                logger.warning(
                    "{} 首次登录失败，重试 {}/{}",
                    self.config.name,
                    attempt + 1,
                    attempts - 1,
                )
        raise AssertionError("unreachable")

    def __exit__(self, *_exc):
        self.close()

    def execute[T](self, operation: Callable[[EamsClient], T]) -> T:
        if self.client is None:
            raise RuntimeError("EAMS client must be opened before use")
        remaining = (
            self.config.auth.retries if isinstance(self.config.auth, SsoAuth) else 0
        )
        while True:
            try:
                return operation(self.client)
            except AuthenticationError:
                while True:
                    if remaining == 0:
                        raise
                    remaining -= 1
                    logger.warning(
                        "{} 会话失效，重新登录（剩余 {} 次）",
                        self.config.name,
                        remaining,
                    )
                    try:
                        self._establish()
                        break
                    except AuthenticationError:
                        continue
                # Only a completed original operation ends this recovery budget.

    def get_course_info(self) -> list[Course]:
        return self.execute(lambda c: c.get_course_info())

    def get_course_status(self) -> dict[str, Capacity]:
        return self.execute(lambda c: c.get_course_status())

    def get_selected_courses(self, courses: list[Course]) -> list[Course]:
        return self.execute(lambda c: c.get_selected_courses(courses))

    def select_course(self, course_id: str) -> SelectionResult:
        return self.execute(lambda c: c.select_course(course_id))

    def get_name(self) -> str:
        return self.execute(lambda c: c.get_name())

    def get_semester_id(self) -> int:
        return self.execute(lambda c: c.get_semester_id())

    def get_profiles(self) -> list[tuple[int, str]]:
        return self.execute(lambda c: c.get_profiles())
