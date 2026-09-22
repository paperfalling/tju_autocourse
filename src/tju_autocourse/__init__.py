"""TJU AutoCourse: typed configuration and synchronous entrypoints."""

from .api import create_user, fetch_courses, run
from .config import AppConfig, ConfigError, UserConfig, load_config

__all__ = [
    "AppConfig",
    "ConfigError",
    "UserConfig",
    "create_user",
    "fetch_courses",
    "load_config",
    "run",
]
