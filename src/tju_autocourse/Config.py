# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:20
# @Author  : papersus
# @File    : Config.py
import json


class Config:
    profileId: int = 3820
    semesterId: int = 116
    domain: str = "classes.tju.edu.cn"
    __courses_info = []
    __course_status = {}

    def __init__(
        self,
        cookie: str,
        profileId: int = profileId,
        semesterId: int = semesterId,
        domain: str = domain,
    ) -> None:
        self.cookie = cookie
        self.profileId = profileId
        self.semesterId = semesterId
        self.domain = domain
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

    @property
    def courses_info(self) -> list[dict]:
        return self.__courses_info

    @property
    def course_status(self) -> dict:
        return self.__course_status

    @classmethod
    def load_courses_info(cls, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
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
            cls.__courses_info.append(
                {
                    "id": str(course_info["id"]),
                    "no": course_info["no"],
                    "name": course_info["name"],
                    "arrangement": course_info["arrangement"],
                    "code": course_info["code"],
                }
            )

    @classmethod
    def set_course_status(cls, status: dict) -> None:
        cls.__course_status = status
