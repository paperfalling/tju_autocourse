# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:57
# @Author  : papersus
# @File    : query.py
import json
import tju_autocourse as atc


if __name__ == "__main__":
    with open("./config/config.json", encoding="utf-8") as f:
        configs = json.load(f)
    user = atc.User(configs[0])
    user.scheduler.query_status()
    print(user.scheduler.course_status)
    with open("./config/status.json", "w", encoding="utf-8") as f:
        json.dump(user.scheduler.course_status, f, ensure_ascii=False, indent=4)
