# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 14:00
# @Author  : papersus
# @File    : course_info.py
import json
import tju_autocourse as atc


if __name__ == "__main__":
    with open("./config/config.json", encoding="utf-8") as f:
        configs = json.load(f)
    user = atc.User(configs[0])
    print(user.config.courses_info)
    with open("./config/course_info.json", "w", encoding="utf-8") as f:
        json.dump(user.config.courses_info, f, ensure_ascii=False, indent=4)
