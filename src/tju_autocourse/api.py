# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 18:49
# @Author  : papersus
# @File    : api.py
import json
import asyncio
from typing import Iterable
from .User import User


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
    return User(config)


def create_users(configs: Iterable[dict]) -> list[User]:
    return [create_user(config) for config in configs]


def set_config_meta(meta: dict) -> None:
    User.Config.set_config_meta(meta)
