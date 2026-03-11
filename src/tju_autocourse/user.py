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
from .user_models import Config, Scheduler, Session

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
    def __init__(self, config: dict) -> None:
        init_logger()
        self.name: str = config["name"]
        logger.info(f"{self.name} 初始化")
        self.config: Config = Config.model_validate(config)
        self.targets: list = config["targets"]
        self.done: list[dict] = []
        self.scheduler: Optional[Scheduler] = None
        self.session: Session = Session(headers=self.config.headers)
        self.timer = time.time()
        logger.success(f"{self.name} 初始化成功")

    async def prepare(self, save_path: Optional[str] = None) -> None:
        async with self.session as session:
            self.config.set_courses_info(await self.query_info(session))
            if not self.config.course_status:
                self.config.set_course_status(await self.query_status(session))
            if save_path is not None:
                info_path = os.path.join(save_path, f"course_info_{self.name}.json")
                statu_path = os.path.join(save_path, f"course_statu_{self.name}.json")
                import json

                with open(info_path, "w", encoding="utf-8") as f:
                    json.dump(self.config.courses_info, f, ensure_ascii=False, indent=4)
                with open(statu_path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.config.course_status, f, ensure_ascii=False, indent=4
                    )
                logger.success(f"{self.name} 课程信息与状态已保存到 {save_path}")
            self.done = await self.query_done(session)
            self.scheduler = Scheduler(self)

    async def wait(self, min_delay: float) -> None:
        await asyncio.sleep(max(0.0, min_delay + self.timer - time.time()))
        self.timer = time.time()

    async def start(self) -> None:
        res = False
        await self.prepare()
        if self.scheduler is None:
            logger.error(f"{self.name} 调度器初始化失败")
            return
        start_time = self.config.startTime.timestamp()
        scheduler = self.scheduler.begin()
        next(scheduler)
        while time.time() < start_time:
            await asyncio.sleep(0.01)
        async with self.session as session:
            logger.info(f"{self.name} 开始选课")
            while True:
                try:
                    course = scheduler.send(res)
                except StopIteration:
                    break
                res = await self.fetch(course, session)

    async def fetch(self, course: dict, session: aiohttp.ClientSession) -> bool:
        url = f"https://{self.config.domain}/eams/stdElectCourse!batchOperator.action?profileId={self.config.profileId}"
        cid, cno, cname = course["id"], course["no"], course["name"]
        data = {"optype": "true", "operator0": f"{cid}:true:0"}
        logger.info(f"{self.name} 尝试选课: {cname}({cno})")
        while True:
            await self.wait(0.5)
            try:
                async with session.post(
                    url,
                    data=data,
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

    async def query_info(self, session: aiohttp.ClientSession) -> list:
        logger.info(f"{self.name} 查询课程信息")
        url = f"https://{self.config.domain}/eams/stdElectCourse!data.action?profileId={self.config.profileId}"
        await self.wait(0.5)
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                status_code = resp.status
                resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error(f"{self.name} 查询课程信息失败: Timeout")
            return []
        if status_code != 200:
            logger.error(f"{self.name} 查询课程信息失败: [{status_code}]")
            return []
        try:
            from .parsers import parse_courses_text

            courses_info = parse_courses_text(resp_text)
        except ValueError as exc:
            logger.error(f"{self.name} 查询课程信息失败: {exc}")
            return []
        logger.success(f"{self.name} 查询课程信息成功")
        return courses_info

    async def query_status(self, session: aiohttp.ClientSession) -> dict:
        url = f"https://{self.config.domain}/eams/stdElectCourse!queryStdCount.action?projectId=1&semesterId={self.config.semesterId}"
        logger.info(f"{self.name} 查询选课状态")
        await self.wait(0.5)
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                status_code = resp.status
                resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error(f"{self.name} 查询选课状态失败: Timeout")
            return {}
        if status_code != 200:
            logger.error(f"{self.name} 查询选课状态失败: [{status_code}]")
            return {}
        try:
            from .parsers import parse_status_text

            courses_status = parse_status_text(resp_text)
        except ValueError as exc:
            logger.error(f"{self.name} 查询选课状态失败: {exc}")
            return {}
        logger.success(f"{self.name} 查询选课状态成功")
        return courses_status

    async def query_done(self, session: aiohttp.ClientSession) -> list[dict]:
        logger.info(f"{self.name} 查询已选课程")
        url1 = "https://classes.tju.edu.cn/eams/courseTableForStd.action"
        await self.wait(0.5)
        try:
            async with session.get(
                url1,
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                status_code = resp.status
                resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error(f"{self.name} 查询已选课程失败: Timeout")
            return []
        if status_code != 200:
            logger.error(f"{self.name} 查询已选课程失败: [{status_code}]")
            return []
        try:
            from .parsers import parse_ids_text

            ids = parse_ids_text(resp_text)
        except ValueError as exc:
            logger.error(f"{self.name} 查询已选课程失败: {exc}")
            return []

        url2 = "https://classes.tju.edu.cn/eams/courseTableForStd!courseTable.action"
        data = {
            "ignoreHead": "1",
            "setting.kind": "std",
            "startWeek": None,
            "semester.id": self.config.semesterId,
            "ids": ids,
        }
        await self.wait(0.5)
        try:
            async with session.post(
                url2,
                data=data,
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                status_code = resp.status
                resp_text = await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.error(f"{self.name} 查询已选课程失败: Timeout")
            return []
        if status_code != 200:
            logger.error(f"{self.name} 查询已选课程失败: [{status_code}]")
            return []
        try:
            from .parsers import parse_done_text

            done = parse_done_text(resp_text)
            done = [
                course
                for course_no in done
                for course in self.config.courses_info
                if course_no == course["no"]
            ]
        except ValueError as exc:
            logger.error(f"{self.name} 查询已选课程失败: {exc}")
            return []
        logger.success(f"{self.name} 查询已选课程成功")
        return done
