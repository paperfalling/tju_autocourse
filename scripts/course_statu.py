# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 14:16
# @Author  : papersus
# @File    : course_statu.py
import json
import tju_autocourse as atc


if __name__ == "__main__":
    with open("./config/config.json", encoding="utf-8") as f:
        configs = json.load(f)
    user = atc.User(configs[0])
    print(user.scheduler.course_status)
    with open("./config/course_statu.json", "w", encoding="utf-8") as f:
        json.dump(user.scheduler.course_status, f, ensure_ascii=False, indent=4)
