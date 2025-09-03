# -*- coding: utf-8 -*-
# @Time    : 2025/09/03 15:46
# @Author  : papersus
# @File    : example.py
import json
import asyncio

import tju_autocourse as atc


async def main() -> None:
    atc.Config.load_courses_info("./config/courses_info.json")
    with open("./config/config.json", encoding="utf-8") as f:
        configs = json.load(f)
    async with asyncio.TaskGroup() as tg:
        for config in configs:
            tg.create_task(atc.User(config).grab())


if __name__ == "__main__":
    asyncio.run(main())
