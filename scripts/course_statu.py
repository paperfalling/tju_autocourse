# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 14:16
# @Author  : papersus
# @File    : course_statu.py
import os
import asyncio
import json
import yaml
import tju_autocourse as atc


async def _main() -> None:
    with open("./config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    atc.set_config_meta(config["meta"])
    user = atc.create_user(config["users"][0])
    await user._setup_session()
    try:
        await user.query_status()
    finally:
        await user._teardown_session()
    print(user.config.course_status)
    if not os.path.exists("./data"):
        os.mkdir("./data")
    with open("./data/course_statu.json", "w", encoding="utf-8") as f:
        json.dump(user.config.course_status, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    asyncio.run(_main())
