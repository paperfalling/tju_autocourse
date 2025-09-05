# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 23:43
# @Author  : papersus
# @File    : test_User.py
from unittest import TestCase
import tju_autocourse as atc
import asyncio
import json

with open("./config.json", encoding="utf-8") as f:
    config = json.load(f)
atc.set_config_meta(config["meta"])
user = atc.create_user(config["users"][0])


class TestUser(TestCase):
    def test_start(self):
        asyncio.run(user.start())

    def test_begin(self):
        for i in user.scheduler.begin():
            print(i)

    def test_check_conflict(self):
        self.assertTrue(
            user.scheduler.check_conflict({"id": "01123", "name": "test", "no": "000"})
        )

    def test_query_status(self):
        self.assertTrue(user.scheduler.course_status)

    def test_load_courses_info(self):
        self.assertTrue(user.config.courses_info)

    def test_headers(self):
        self.assertEqual(user.config.headers["Cookie"], config["users"][0]["cookie"])
