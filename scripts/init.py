# -*- coding: utf-8 -*-
"""
初始化配置向导 (Interactive Config Initialization)
运行此脚本可以避免手动抓包寻找 profileId 和 semesterId
"""

import os
import yaml
import asyncio
import aiohttp

CONFIG_PATH = "./config.yaml"


async def fetch(user: dict, meta: dict, num: int):
    cookie = user.get("cookie", "")
    if not cookie or cookie == "your_cookie":
        print(f"用户 {num} 的 cookie 未设置")
        return {}
    name = user.get("name", f"user{num}")
    profile_id = meta.get("profileId", 0)
    profile_id = user.get("profileId", profile_id)
    semester_id = meta.get("semesterId", 0)
    semester_id = user.get("semesterId", semester_id)
    skipPre = meta.get("skipPre", False)
    skipPre = user.get("skipPre", skipPre)

    domain = meta["domain"]
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "max-age=0",
        "Origin": f"https://{domain}",
        "x-requested-with": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": f"https://{domain}/eams/stdElectCourse!defaultPage.action",
        "Cookie": cookie,
    }

    from lxml import html
    import re

    etree = html.etree

    async def get_name():
        url = f"https://{domain}/eams/homeExt.action"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"请求失败，状态码: {resp.status}")
                    text = etree.HTML(await resp.text())
                    name = text.xpath('//*[@id="main-top"]/div/div/div/a/text()')
                    return name[0].strip() if name else f"user{num}"
        except aiohttp.ClientError:
            print(f"用户 {num} 的 cookie 无效，无法获取用户名")
            return f"user{num}"

    async def get_semester_id():
        m = re.match(r"semester.id=(\d+)", cookie)
        if m:
            return int(m.group(1))
        url = f"https://{domain}/eams/courseTableForStd.action"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"请求失败，状态码: {resp.status}")
                    return int(resp.cookies["semester.id"].value)
        except aiohttp.ClientError:
            print(f"用户 {num} 的 cookie 无效，无法获取 semesterId")
            return 0

    async def get_profile_id():
        url = f"https://{domain}/eams/stdElectCourse.action"
        try:
            profiles = []
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientError(f"请求失败，状态码: {resp.status}")
                    text = etree.HTML(await resp.text())
                    divs = text.xpath("/html/body/div[1]/div")
                    for div in divs:
                        h = div.xpath("./h2")[0].text
                        i = div.xpath("./div[last()]/form/input")
                        if i:
                            profiles.append((int(i[0].get("value")), h))
                        else:
                            m = re.search(
                                r"electionProfile.id=(\d+)",
                                div.xpath("./script")[0].text,
                            )
                            if m:
                                profiles.append((int(m.group(1)), h))
                    if not profiles:
                        raise ValueError("未找到 profileId")
            if not profiles:
                print("暂未找到选课项目")
                return 0
            if len(profiles) == 1:
                print(f"已找到唯一选课项目: {profiles[0][1]} ({profiles[0][0]})")
                return profiles[0][0]
            print("请选择选课项目:")
            for idx, (pid, pname) in enumerate(profiles, start=1):
                print(f"{idx}. {pname} ({pid})")
            while True:
                choice = input("请输入选课项目编号 (默认 1): ").strip()
                if not choice:
                    return profiles[0][0]
                if choice.isdigit() and 1 <= int(choice) <= len(profiles):
                    return profiles[int(choice) - 1][0]
                print("输入无效，请重新输入")
        except aiohttp.ClientError:
            print(f"用户 {num} 的 cookie 无效，无法获取 profileId")
            return 0

    if not name:
        name = await get_name()
    if not semester_id:
        semester_id = await get_semester_id()
    if not profile_id:
        profile_id = await get_profile_id()

    user.update(
        {
            "name": name,
            "profileId": profile_id,
            "semesterId": semester_id,
            "skipPre": skipPre,
        }
    )
    return user


async def main():
    if not os.path.exists(CONFIG_PATH):
        with open("config.template.yaml", encoding="utf-8") as f:
            template = f.read()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"已创建配置文件 {CONFIG_PATH}，请编辑后重新运行此脚本")
        return

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    meta = config.get("meta", {})
    meta["domain"] = meta.get("domain", "classes.tju.edu.cn")
    import datetime

    meta["startTime"] = meta.get("startTime", datetime.datetime(1970, 1, 1, 8, 0, 0))
    if isinstance(meta["startTime"], str):
        try:
            meta["startTime"] = datetime.datetime.strptime(
                meta["startTime"], "%Y-%m-%dT%H:%M:%S"
            )
        except ValueError:
            pass
    config["users"] = await asyncio.gather(
        *(
            fetch(user, meta, num)
            for num, user in enumerate(config.get("users", []), start=1)
        )
    )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print("初始化完成, 配置已自动更新至 config.yaml")


if __name__ == "__main__":
    asyncio.run(main())
