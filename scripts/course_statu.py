# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 14:16
# @Author  : papersus
# @File    : course_statu.py
import json
import os
import tju_autocourse as atc


if __name__ == "__main__":
    with open("./config.json", encoding="utf-8") as f:
        config = json.load(f)
    atc.set_config_meta(config["meta"])
    user = atc.create_user(config["users"][0])
    print(user.scheduler.course_status)
    if not os.path.exists("./data"):
        os.mkdir("./data")
    with open("./data/course_statu.json", "w", encoding="utf-8") as f:
        json.dump(user.scheduler.course_status, f, ensure_ascii=False, indent=4)
