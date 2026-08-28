from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import aiohttp
from lxml import html
from loguru import logger

from tju_autocourse.api import create_user
from tju_autocourse.config import merge_user_config, set_config_meta
from tju_autocourse.parsers import _normalize_json_like
from tju_autocourse.user import User
from tju_autocourse.user_models import Scheduler


WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class WebUser(User):
    """User adapter that tolerates malformed course rows without changing core code."""

    async def prepare(self, save_path: str | None = None) -> None:
        del save_path  # Web tasks do not write per-run course files.
        cached_info, cached_status = load_cached_courses(self.name)
        async with self.session as session:
            try:
                course_info = await fetch_course_info_tolerant(self, session)
                if not course_info:
                    raise ValueError("学校接口没有返回课程信息")
            except Exception as exc:  # noqa: BLE001 - local cache is the safe fallback
                logger.warning(f"{self.name} 在线课程解析失败，使用本地缓存：{type(exc).__name__}")
                course_info = cached_info
            if not course_info:
                raise ValueError(f"{self.name} 无法获取课程信息，请更新 Cookie 或课程缓存")
            self.config.set_courses_info(course_info)

            course_status = await self.query_status(session)
            if not course_status:
                course_status = cached_status
                if course_status:
                    logger.warning(f"{self.name} 在线余量解析失败，使用本地缓存")
            if not course_status and not self.config.skipPre:
                raise ValueError(f"{self.name} 无法获取课程余量，请更新 Cookie 或开启跳过余量预检")
            self.config.set_course_status(course_status)
            self.done = await self.query_done(session)
            self.scheduler = Scheduler(self)


def create_web_users(configs: list[dict[str, Any]]) -> list[WebUser]:
    return [WebUser(merge_user_config(config)) for config in configs]


def account_headers(account: dict[str, Any]) -> dict[str, str]:
    domain = account.get("domain") or "classes.tju.edu.cn"
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": f"https://{domain}",
        "x-requested-with": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
        "Referer": f"https://{domain}/eams/stdElectCourse!defaultPage.action",
        "Cookie": str(account.get("cookie", "")),
    }


async def initialize_account(account: dict[str, Any]) -> dict[str, Any]:
    result = dict(account)
    domain = result.get("domain") or "classes.tju.edu.cn"
    result["domain"] = domain
    if not result.get("semesterId"):
        semester_match = re.search(r"(?:^|;\s*)semester\.id=(\d+)", str(result.get("cookie", "")))
        if semester_match:
            result["semesterId"] = int(semester_match.group(1))
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(headers=account_headers(result), timeout=timeout) as session:
        async with session.get(f"https://{domain}/eams/homeExt.action") as response:
            if response.status != 200:
                raise ValueError(f"登录验证失败，状态码 {response.status}")
            tree = html.fromstring(await response.text())
            names = tree.xpath('//*[@id="main-top"]/div/div/div/a/text()')
            if names:
                result["name"] = names[0].strip()

        if not result.get("semesterId"):
            async with session.get(f"https://{domain}/eams/courseTableForStd.action") as response:
                if response.status != 200:
                    raise ValueError(f"无法读取学期信息，状态码 {response.status}")
                semester_cookie = response.cookies.get("semester.id")
                if semester_cookie:
                    result["semesterId"] = int(semester_cookie.value)

        if not result.get("profileId"):
            async with session.get(f"https://{domain}/eams/stdElectCourse.action") as response:
                if response.status != 200:
                    raise ValueError(f"无法读取选课轮次，状态码 {response.status}")
                tree = html.fromstring(await response.text())
                profile_ids = tree.xpath('//form//input[@name="electionProfile.id"]/@value')
                if not profile_ids:
                    scripts = "\n".join(tree.xpath("//script/text()"))
                    profile_ids = re.findall(r"electionProfile\.id=(\d+)", scripts)
                if profile_ids:
                    result["profileId"] = int(profile_ids[0])

    if not result.get("profileId") or not result.get("semesterId"):
        raise ValueError("凭证有效，但没有找到当前学期或选课轮次")
    return result


def arrangement_text(arrangements: list[Any]) -> str:
    if not arrangements:
        return "时间待定"
    parts: list[str] = []
    for item in arrangements:
        if len(item) < 4:
            continue
        day = int(item[1])
        weekday = WEEKDAYS[day - 1] if 1 <= day <= 7 else f"周{day}"
        parts.append(f"{weekday} {item[2]}-{item[3]}节")
    return "；".join(parts) or "时间待定"


def public_course(course: dict[str, Any], status: dict[str, Any] | None = None) -> dict[str, Any]:
    status = status or {}
    selected = int(status.get("sc", 0) or 0)
    capacity = int(status.get("lc", 0) or 0)
    return {
        "id": str(course.get("id", "")),
        "no": str(course.get("no", "")),
        "code": str(course.get("code", "")),
        "name": str(course.get("name", "未命名课程")),
        "teacher": str(course.get("teacher", "待定")),
        "credits": float(course.get("credits", 0) or 0),
        "campus": str(course.get("campus", "校区待定")),
        "schedule": arrangement_text(course.get("arrangement", [])),
        "selected": selected,
        "capacity": capacity,
        "available": capacity == 0 or selected < capacity,
    }


async def fetch_courses(account: dict[str, Any], meta: dict[str, Any]) -> list[dict[str, Any]]:
    set_config_meta(meta)
    user = create_user(account)
    try:
        async with user.session as session:
            course_info = await fetch_course_info_tolerant(user, session)
            course_status = await user.query_status(session)
        if not course_info:
            raise ValueError("学校接口没有返回课程信息")
    except Exception as exc:  # noqa: BLE001 - cached data keeps WebUI usable
        logger.warning(f"在线课程同步失败，尝试使用本地缓存：{type(exc).__name__}")
        course_info, course_status = load_cached_courses(str(account.get("name", "")))
        if not course_info:
            raise ValueError("课程同步失败，请重新验证账号或先运行 course_fetch.py 生成本地缓存") from exc
    return [public_course(course, course_status.get(str(course["id"]))) for course in course_info]


async def fetch_course_info_tolerant(user: Any, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    url = f"https://{user.config.domain}/eams/stdElectCourse!data.action?profileId={user.config.profileId}"
    await user.wait(0.5)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
        if response.status != 200:
            raise ValueError(f"课程接口返回状态码 {response.status}")
        response_text = await response.text()
    # 课程数组位于单独的脚本行中；限制为单行可避开页面中其他 JS 数组。
    matches = re.findall(r"\[.*\]", response_text)
    if not matches:
        raise ValueError("课程接口未返回有效数据")
    raw_courses: list[Any] = []
    best_score = 0
    for candidate in matches:
        try:
            parsed = json.loads(_normalize_json_like(candidate))
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        score = sum(
            1 for item in parsed
            if isinstance(item, dict) and {"id", "no", "name", "code"}.issubset(item)
        )
        if score > best_score:
            raw_courses = parsed
            best_score = score
    if not raw_courses:
        raise ValueError("课程接口数据结构无法识别")
    courses: list[dict[str, Any]] = []
    for raw_course in raw_courses:
        if not isinstance(raw_course, dict):
            continue
        arrangements: list[tuple[int, int, int, int]] = []
        arrange_info = raw_course.get("arrangeInfo", [])
        if isinstance(arrange_info, list):
            for item in arrange_info:
                if not isinstance(item, dict):
                    continue
                try:
                    arrangements.append(
                        (
                            int(str(item["weekState"]), base=2),
                            int(item["weekDay"]),
                            int(item["startUnit"]),
                            int(item["endUnit"]),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        if not all(key in raw_course for key in ("id", "no", "name", "code")):
            continue
        courses.append(
            {
                "id": str(raw_course["id"]),
                "no": str(raw_course["no"]),
                "name": str(raw_course["name"]),
                "arrangement": arrangements,
                "code": str(raw_course["code"]),
            }
        )
    return courses


def load_cached_courses(account_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    safe_name = re.sub(r"[^\w.-]", "_", account_name, flags=re.UNICODE)
    if not safe_name:
        return [], {}
    data_dir = PROJECT_ROOT / "data"
    info_path = data_dir / f"course_info_{safe_name}.json"
    status_path = data_dir / f"course_statu_{safe_name}.json"
    if not info_path.exists():
        return [], {}
    try:
        with info_path.open(encoding="utf-8") as file:
            info = json.load(file)
        status: dict[str, Any] = {}
        if status_path.exists():
            with status_path.open(encoding="utf-8") as file:
                status = json.load(file)
        return info if isinstance(info, list) else [], status if isinstance(status, dict) else {}
    except (OSError, json.JSONDecodeError):
        return [], {}
