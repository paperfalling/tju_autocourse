# @Time    : 2025/09/05 18:49
# @Author  : papersus
# @File    : api.py
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from loguru import logger

from .logging import init_logger
from .models import merge_user_config, set_config_meta, validate_config
from .user import User


def create_user(config: dict) -> User:
    merged_config = merge_user_config(config)
    return User(merged_config)


def create_users(configs: Iterable[dict]) -> list[User]:
    return [create_user(config) for config in configs]


def get_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    validate_config(config)
    return config


def _work(config_path: str) -> None:
    config = get_config(config_path)
    set_config_meta(config["meta"])
    users = create_users(config["users"])
    with ThreadPoolExecutor(max_workers=max(1, len(users))) as executor:
        futures = {executor.submit(user.run): user for user in users}
        for future in as_completed(futures):
            user = futures[future]
            try:
                future.result()
            except Exception:  # noqa: BLE001
                logger.exception("User {} failed; continuing other users", user.name)


def run(config_path: str) -> None:
    init_logger()
    _work(config_path)
