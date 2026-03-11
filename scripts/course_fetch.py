# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 14:16
# @Author  : papersus
# @File    : course_fetch.py
import asyncio
import tju_autocourse as atc


async def _main() -> None:
    config = atc.get_config("./config.yaml")
    atc.set_config_meta(config["meta"])
    users = atc.create_users(config["users"])
    await asyncio.gather(*(user.prepare(save_path="./data") for user in users))


if __name__ == "__main__":
    asyncio.run(_main())
