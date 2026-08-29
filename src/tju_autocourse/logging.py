import sys
from os import makedirs
from threading import Lock

from loguru import logger

LOG_FORMAT = "<green>{time:HH:mm:ss}</green> | <cyan>{name}:{function}:L{line}</cyan> | <level>{level: <8}</level> | <level>{message}</level>"
_LOGGER_INITIALIZED = False
_LOGGER_LOCK = Lock()


def init_logger() -> None:
    """Configure the process-wide application logger once."""
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return
    with _LOGGER_LOCK:
        if _LOGGER_INITIALIZED:
            return
        makedirs("./logs", exist_ok=True)
        logger.remove()
        logger.add(sys.stdout, format=LOG_FORMAT)
        logger.add(
            "./logs/{time:YYYY-MM-DD_HH-mm-ss}.log",
            mode="w",
            format=LOG_FORMAT,
        )
        _LOGGER_INITIALIZED = True
