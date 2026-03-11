# -*- coding: utf-8 -*-
# @Time    : 2025/09/25 14:07
# @Author  : papersus
# @File    : check_course.py
import yaml
import os


if __name__ == "__main__":
    print("正在检查选课计划...")
    print("想刷新课程状态请重新运行 scripts/course_fetch.py")
    if not os.path.exists("./config.yaml"):
        raise FileNotFoundError("请确保 config.yaml 文件存在")
    with open("./config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    for user in config["users"]:
        name = user["name"]
        print(f"用户 {name} 选课计划: ")
        if not os.path.exists(f"./data/course_statu_{name}.json"):
            raise FileNotFoundError("请先运行 scripts/course_statu.py 以获取课程状态")
        if not os.path.exists(f"./data/course_info_{name}.json"):
            raise FileNotFoundError("请先运行 scripts/course_info.py 以获取课程信息")
        with open(f"./data/course_statu_{name}.json", encoding="utf-8") as f:
            course_statu = yaml.safe_load(f)
        with open(f"./data/course_info_{name}.json", encoding="utf-8") as f:
            course_info = yaml.safe_load(f)
        targets = user["targets"]
        for group in targets:
            print(f"  组 {group['group_name']} (限制: {group['limit']}):")
            for no in group["courses"]:
                course = next((c for c in course_info if c["no"] == no), None)
                if not course:
                    print(f"    课程代码 {no} 未找到课程信息")
                    continue
                statu = course_statu.get(course["id"], {})
                print(f"    课程 {course['name']} ({no}):")
                print(f"      课程序号: {course['no']}")
                print(f"      课程代码: {course['code']}")
                print(f"      课程安排: {course['arrangement']}")
                if not statu:
                    print("      课程状态信息未找到")
                    continue
                print(f"      课程总容量: {statu.get('lc', '未知')}")
                print(f"      课程已选人数: {statu.get('sc', '未知')}")
                print(f"      是否开放计划外: {statu.get('unplan', '未知')}")
            print()
