# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 23:43
# @Author  : papersus
# @File    : test_User.py
from unittest import TestCase
from tju_autocourse import User, Scheduler, Config
import asyncio
import json
import time

with open("./config/config.json", encoding="utf-8") as f:
    configs = json.load(f)
Config.load_courses_info("./config/courses_info.json")
user = User(configs[0])
schedule = Scheduler(user)


class TestUser(TestCase):
    def test_grab(self):
        time.sleep(1)
        asyncio.run(user.grab())


class TestScheduler(TestCase):
    def test_begin(self):
        for i in schedule.begin():
            print(i)

    def test_check_conflict(self):
        self.assertTrue(schedule.check_conflict({"id": "01123"}))

    def test_query_status(self):
        schedule.course_status
