# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 23:43
# @Author  : papersus
# @File    : test_Config.py
from unittest import TestCase
from tju_autocourse.Config import Config

config = Config("cookie")


class TestConfig(TestCase):
    def test_load_courses_info(self):
        config.load_courses_info("./config/courses_info.json")

    def test_headers(self):
        self.assertEqual(config.headers["Cookie"], "cookie")
