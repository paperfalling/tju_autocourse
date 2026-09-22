"""Logging is initialized by entrypoints, never during imports or construction."""

import sys
from pathlib import Path

from loguru import logger

_initialized = False


def init_logger():
    global _initialized
    if _initialized:
        return
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    format_string = "{time:HH:mm:ss} | {level: <8} | {message}"
    logger.add(sys.stdout, format=format_string, diagnose=False, backtrace=False)
    logger.add(
        "logs/{time:YYYY-MM-DD_HH-mm-ss_SSS}.log",
        format=format_string,
        diagnose=False,
        backtrace=False,
    )
    _initialized = True
