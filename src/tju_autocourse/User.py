# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:26
# @Author  : papersus
# @File    : User.py
import asyncio
import time
import json
import re
from typing import Optional, Generator

import aiohttp
import requests

from tju_autocourse import Config


class User:
    def __init__(self, config: dict) -> None:
        self.config: Config = Config(config["cookie"])
        self.name: str = config["name"]
        self.tsl: dict[str, int] = config["tags_sort_limit"]
        self.courses: dict[str, list[str]] = config["courses"]
        if domain := config.get("domain"):
            self.config.domain = domain
        if profileId := config.get("profileId"):
            self.config.profileId = profileId
        if semesterId := config.get("semesterId"):
            self.config.semesterId = semesterId
        self.scheduler: Scheduler = Scheduler(self)
        self.url = f"http://{self.config.domain}/eams/stdElectCourse!batchOperator.action?profileId={self.config.profileId}"

    async def grab(self) -> None:
        res = False
        last_time = 0
        scheduler = self.scheduler.begin()
        next(scheduler)
        while True:
            try:
                course = scheduler.send(res)
            except StopIteration:
                break
            cid, cno, cname = course["id"], course["no"], course["name"]
            data = {"optype": "true", "operator0": f"{cid}:true:0"}
            while True:
                res = False
                if last_time:
                    await asyncio.sleep(max(0.0, 0.55 + last_time - time.time()))
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            self.url,
                            data=data,
                            headers=self.config.headers,
                            timeout=aiohttp.ClientTimeout(total=1),
                        ) as resp:
                            resp = await resp.text()
                            last_time = time.time()
                            if "成功" in resp:
                                print(f"{self.name} 选课成功: {cname}({cno})")
                                res = True
                            elif "过快" in resp:
                                print(f"{self.name} 点击过快: {cname}({cno})")
                                continue
                            elif "不开放" in resp:
                                print(f"{self.name} 选课不开放: {cname}({cno})")
                                continue
                            elif "已满" in resp:
                                print(f"{self.name} 选课已满: {cname}({cno})")
                            elif "选过" in resp:
                                print(f"{self.name} 选课已选过: {cname}({cno})")
                            break
                except asyncio.TimeoutError:
                    print(f"{self.name} 请求超时: {cname}({cno})")
                    break


class Scheduler:
    def __init__(self, user: User) -> None:
        self.user = user
        self.courses = {
            tag: [
                course
                for course_no in user.courses[tag]
                for course in self.user.config.courses_info
                if course_no == course["no"]
            ]
            for tag in user.courses
        }
        self.done = []

    def begin(self) -> Generator[dict, bool, None]:
        yield {}
        for tag in self.user.tsl:
            num = 0
            for course in self.courses[tag]:
                if num >= self.user.tsl[tag] >= 0:
                    break
                if self.check_conflict(course):
                    continue
                if (yield course):
                    self.done.append(course)
                    num += 1
        return

    def check_conflict(self, course: dict) -> bool:
        current_info: Optional[dict] = self.course_status.get(course["id"])
        if current_info is None:
            return True
        if current_info["sc"] >= current_info["lc"]:
            return True
        for dc in self.done:
            if dc["code"] == course["code"]:
                return True
            for i in dc["arrangement"]:
                for j in course["arrangement"]:
                    if (
                        i[0] & j[0]
                        and i[1] == j[1]
                        and max(i[2], j[2]) <= min(i[3], j[3])
                    ):
                        return True
        return False

    def query_status(self) -> None:
        url = f"http://{self.user.config.domain}/eams/stdElectCourse!queryStdCount.action?projectId=1&semesterId={self.user.config.semesterId}"
        try:
            resp = requests.get(url, headers=self.user.config.headers, timeout=2)
        except requests.exceptions.Timeout:
            print("查询选课信息失败: Timeout")
            return
        if resp.status_code != 200:
            print("查询选课信息失败: ", {resp.status_code})
            return
        resp_text = resp.text[44:].replace("'", '"')
        resp_text = re.sub(r"([a-z]+)(?=:)", r'"\1"', resp_text)
        Config.set_course_status(json.loads(resp_text))

    @property
    def course_status(self) -> dict:
        if not self.user.config.course_status:
            self.query_status()
        return self.user.config.course_status
