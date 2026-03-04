# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 18:49
# @Author  : papersus
# @File    : api.py
import json
import asyncio
from typing import Iterable
from .user import User


_config_meta = {
    "profileId": 0,
    "semesterId": 0,
    "domain": "classes.tju.edu.cn",
    "startTime": "1970-01-01T08:00:00",
    "skipPre": False,
}


async def _work(config_path: str) -> None:
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    set_config_meta(config["meta"])
    async with asyncio.TaskGroup() as tg:
        for user in create_users(config["users"]):
            tg.create_task(user.start())


def run(config_path: str) -> None:
    asyncio.run(_work(config_path))


def create_user(config: dict) -> User:
    merged_config = config.copy()
    for key, value in _config_meta.items():
        merged_config.setdefault(key, value)
    return User(merged_config)


def create_users(configs: Iterable[dict]) -> list[User]:
    return [create_user(config) for config in configs]


def set_config_meta(meta: dict) -> None:
    _config_meta.update(meta)
