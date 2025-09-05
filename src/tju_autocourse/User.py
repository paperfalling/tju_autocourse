# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:26
# @Author  : papersus
# @File    : User.py
import asyncio
import time
import json
import sys
import re
from typing import Optional, Generator

import aiohttp
import requests
from loguru import logger

format = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
logger.remove()
logger.add(sys.stdout, format=format)
logger.add("./log", mode="w", format=format)


class User:
    def __init__(self, config: dict) -> None:
        self.name = config["name"]
        logger.info(f"{self.name} 初始化")
        self.config = User.Config(config["name"], config["cookie"])
        self.tsl = config["tags_sort_limit"]
        self.courses = config["courses"]
        self.scheduler = User.Scheduler(self)
        self.timer = time.time()
        logger.success(f"{self.name} 初始化成功")

    async def start(self) -> None:
        res = False
        scheduler = self.scheduler.begin()
        next(scheduler)
        while True:
            try:
                course = scheduler.send(res)
            except StopIteration:
                break
            res = await self.grab(course)

    async def grab(self, course: dict) -> bool:
        url = f"http://{self.config.domain}/eams/stdElectCourse!batchOperator.action?profileId={self.config.profileId}"
        cid, cno, cname = course["id"], course["no"], course["name"]
        data = {"optype": "true", "operator0": f"{cid}:true:0"}
        logger.info(f"{self.name} 尝试选课: {cname}({cno})")
        while True:
            await asyncio.sleep(max(0.0, 0.5 + self.timer - time.time()))
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        data=data,
                        headers=self.config.headers,
                        timeout=aiohttp.ClientTimeout(total=1),
                    ) as resp:
                        resp = await resp.text()
                        self.timer = time.time()
                        if "成功" in resp:
                            logger.success(f"{self.name} 选课成功: {cname}({cno})")
                            return True
                        elif "过快" in resp:
                            logger.warning(f"{self.name} 点击过快: {cname}({cno})")
                        elif "不开放" in resp:
                            logger.warning(f"{self.name} 选课不开放: {cname}({cno})")
                        elif "已满" in resp:
                            logger.warning(f"{self.name} 选课已满: {cname}({cno})")
                            return False
                        elif "选过" in resp:
                            logger.warning(f"{self.name} 选课已选过: {cname}({cno})")
                            return False
            except asyncio.TimeoutError:
                logger.error(f"{self.name} 请求超时: {cname}({cno})")
                return False

    def query_status(self) -> None:
        url = f"http://{self.config.domain}/eams/stdElectCourse!queryStdCount.action?projectId=1&semesterId={self.config.semesterId}"
        logger.info("查询选课状态")
        try:
            time.sleep(max(0.0, 0.5 + self.timer - time.time()))
            resp = requests.get(url, headers=self.config.headers, timeout=2)
            self.timer = time.time()
        except requests.exceptions.Timeout:
            logger.error("查询选课状态失败: Timeout")
            return
        if resp.status_code != 200:
            logger.error("查询选课状态失败: ", f"[{resp.status_code}]")
            return
        resp_text = resp.text[44:].replace("'", '"')
        resp_text = re.sub(r"([a-zA-Z]+)(?=:)", r'"\1"', resp_text)
        with logger.catch(json.JSONDecodeError):
            User.Config.set_course_status(json.loads(resp_text))
        logger.success("查询选课状态成功")

    class Config:
        __profileId: int = 0
        __semesterId: int = 0
        __domain: str = ""
        __course_status: dict = {}

        def __init__(
            self,
            name: str,
            cookie: str,
        ) -> None:
            self.cookie = cookie
            self.name = name
            self.headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cache-Control": "no-cache",
                "Content-Length": "39",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Host": self.domain,
                "Origin": f"http://{self.domain}",
                "Pragma": "no-cache",
                "x-requested-with": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Referer": f"http://{self.domain}/eams/stdElectCourse!defaultPage.action",
                "Cookie": self.cookie,
            }
            self.courses_info = self.query_courses_info()

        def query_courses_info(self) -> list:
            logger.info(f"{self.name} 查询课程信息")
            url = f"http://{self.domain}/eams/stdElectCourse!data.action?profileId={self.profileId}"
            try:
                resp = requests.get(url, headers=self.headers, timeout=3)
            except requests.exceptions.Timeout:
                logger.error(f"{self.name} 查询课程信息失败: Timeout")
                return []
            if resp.status_code != 200:
                logger.error(f"{self.name} 查询课程信息失败: ", f"[{resp.status_code}]")
                return []
            resp_text = resp.text[18:-1].replace("'", '"')
            resp_text = re.sub(r"([a-zA-Z]+)(?=:)", r'"\1"', resp_text)
            with logger.catch(json.JSONDecodeError):
                data = json.loads(resp_text)
            courses_info = []
            for course_info in data:
                course_info["arrangement"] = [
                    (
                        int(j["weekState"], base=2),
                        j["weekDay"],
                        j["startUnit"],
                        j["endUnit"],
                    )
                    for j in course_info["arrangeInfo"]
                ]
                courses_info.append(
                    {
                        "id": str(course_info["id"]),
                        "no": course_info["no"],
                        "name": course_info["name"],
                        "arrangement": course_info["arrangement"],
                        "code": course_info["code"],
                    }
                )
            logger.success(f"{self.name} 查询课程信息成功")
            return courses_info

        @property
        def course_status(self) -> dict:
            return self.__course_status

        @property
        def profileId(self) -> int:
            return self.__profileId

        @property
        def semesterId(self) -> int:
            return self.__semesterId

        @property
        def domain(self) -> str:
            return self.__domain

        @classmethod
        def set_course_status(cls, status: dict) -> None:
            cls.__course_status = status

        @classmethod
        def set_config_meta(cls, meta: dict) -> None:
            cls.__profileId = meta["profileId"]
            cls.__semesterId = meta["semesterId"]
            cls.__domain = meta["domain"]

    class Scheduler:
        def __init__(self, user: "User") -> None:
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
                        logger.info(f"{self.user.name} {tag} 选课数量已达上限")
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
                logger.warning(
                    f"{self.user.name} 未查询到课程信息: {course['name']}({course['no']})"
                )
                return True
            if current_info["sc"] >= current_info["lc"]:
                logger.warning(
                    f"{self.user.name} 选课已满: {course['name']}({course['no']})"
                )
                return True
            for dc in self.done:
                if dc["code"] == course["code"]:
                    logger.warning(
                        f"{self.user.name} 已选过同课程代码课程: {course['name']}({course['no']})"
                    )
                    return True
                for i in dc["arrangement"]:
                    for j in course["arrangement"]:
                        if (
                            i[0] & j[0]
                            and i[1] == j[1]
                            and max(i[2], j[2]) <= min(i[3], j[3])
                        ):
                            logger.warning(
                                f"{self.user.name} 课程时间冲突: {course['name']}({course['no']})"
                            )
                            return True
            return False

        @property
        def course_status(self) -> dict:
            if not self.user.config.course_status:
                self.user.query_status()
            return self.user.config.course_status
