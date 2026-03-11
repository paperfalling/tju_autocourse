# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 18:49
# @Author  : papersus
# @File    : api.py
import asyncio
import yaml
from typing import Iterable
from .user import User, init_logger
from .config import (
    validate_config,
    merge_user_config,
    set_config_meta,
)


def get_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    validate_config(config)
    return config


async def _work(config_path: str) -> None:
    config = get_config(config_path)
    set_config_meta(config["meta"])
    async with asyncio.TaskGroup() as tg:
        for user in create_users(config["users"]):
            tg.create_task(user.start())


def run(config_path: str) -> None:
    init_logger()
    asyncio.run(_work(config_path))


def create_user(config: dict) -> User:
    merged_config = merge_user_config(config)
    return User(merged_config)


def create_users(configs: Iterable[dict]) -> list[User]:
    return [create_user(config) for config in configs]
