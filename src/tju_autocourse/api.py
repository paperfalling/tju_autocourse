"""Synchronous application entrypoints with isolated per-user workers."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

from .config import UserConfig, load_config
from .errors import AutoCourseError
from .logging import init_logger
from .user import User


def create_user(config: UserConfig) -> User:
    return User(config)


def run_users(users, *, snapshot_path=None) -> bool:
    succeeded = True
    pool = ThreadPoolExecutor(
        max_workers=max(1, len(users)), thread_name_prefix="course-user"
    )
    try:
        futures = {
            pool.submit(
                user.run if snapshot_path is None else user.prepare,
                **({} if snapshot_path is None else {"save_path": snapshot_path}),
            ): user
            for user in users
        }
        for future in as_completed(futures):
            user = futures[future]
            try:
                future.result()
            except Exception as exc:
                succeeded = False
                # Unknown exception text/tracebacks may contain credentials or URLs.
                detail = (
                    str(exc) if isinstance(exc, AutoCourseError) else type(exc).__name__
                )
                logger.error("{} 运行失败: {}", user.name, detail)
    except KeyboardInterrupt:
        for user in users:
            user.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return succeeded


def run(config_path: str) -> bool:
    init_logger()
    config = load_config(config_path)
    return run_users([create_user(user) for user in config.users])


def fetch_courses(config_path="./config.yaml", directory="./data") -> bool:
    init_logger()
    config = load_config(config_path)
    return run_users(
        [create_user(user) for user in config.users], snapshot_path=directory
    )
