# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:26
# @Author  : papersus
# @File    : user.py
import asyncio
import time
import sys
import os
from typing import Optional

import aiohttp
from loguru import logger
from .parsers import parse_status_text
from .user_models import Config, Scheduler

LOG_FORMAT = "<green>{time:HH:mm:ss}</green> | <cyan>{name}:{function}:L{line}</cyan> | <level>{level: <8}</level> | <level>{message}</level>"
_LOGGER_INITIALIZED = False


def init_logger() -> None:
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return
    os.makedirs("./logs", exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, format=LOG_FORMAT)
    logger.add("./logs/{time:YYYY-MM-DD_HH-mm-ss}.log", mode="w", format=LOG_FORMAT)
    _LOGGER_INITIALIZED = True


class User:
    Config = Config
    Scheduler = Scheduler

    def __init__(self, config: dict) -> None:
        init_logger()
        self.name = config["name"]
        logger.info(f"{self.name} 初始化")
        self.config = Config(
            config["name"],
            config["cookie"],
            config.get("profileId"),
            config.get("semesterId"),
            config.get("domain"),
            config.get("startTime"),
            config.get("skipPre"),
        )
        self.targets = config["targets"]
        self.scheduler: Optional[Scheduler] = None
        self.timer = time.time()
        logger.success(f"{self.name} 初始化成功")

    async def prepare(self) -> None:
        self.config.courses_info = await self.config.query_courses_info()
        self.scheduler = Scheduler(self)

    async def start(self) -> None:
        res = False
        await self.prepare()
        async with aiohttp.ClientSession() as session:
            if not self.config.skipPre and not self.config.course_status:
                await self.query_status()
            if self.scheduler is None:
                logger.error(f"{self.name} 调度器初始化失败")
                return
            scheduler = self.scheduler.begin()
            next(scheduler)
            while time.time() < self.config.startTime:
                await asyncio.sleep(0.01)
            logger.info(f"{self.name} 开始选课")
            while True:
                try:
                    course = scheduler.send(res)
                except StopIteration:
                    break
                res = await self.grab(course, session)

    async def grab(self, course: dict, session: aiohttp.ClientSession) -> bool:
        url = f"https://{self.config.domain}/eams/stdElectCourse!batchOperator.action?profileId={self.config.profileId}"
        cid, cno, cname = course["id"], course["no"], course["name"]
        data = {"optype": "true", "operator0": f"{cid}:true:0"}
        logger.info(f"{self.name} 尝试选课: {cname}({cno})")
        while True:
            await asyncio.sleep(max(0.0, 0.5 + self.timer - time.time()))
            self.timer = time.time()
            try:
                async with session.post(
                    url,
                    data=data,
                    headers=self.config.headers,
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    resp = await resp.text()
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
            except (asyncio.TimeoutError, aiohttp.ClientError):
                logger.error(f"{self.name} 请求超时: {cname}({cno})")
                return False

    async def query_status(self) -> None:
        url = f"https://{self.config.domain}/eams/stdElectCourse!queryStdCount.action?projectId=1&semesterId={self.config.semesterId}"
        logger.info("查询选课状态")
        await asyncio.sleep(max(0.0, 0.5 + self.timer - time.time()))
        self.timer = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.config.headers,
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    status_code = resp.status
                    resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error("查询选课状态失败: Timeout")
            return
        if status_code != 200:
            logger.error(f"查询选课状态失败: [{status_code}]")
            return
        try:
            self.config.set_course_status(parse_status_text(resp_text))
        except ValueError as exc:
            logger.error(f"查询选课状态失败: {exc}")
            return
        logger.success("查询选课状态成功")
