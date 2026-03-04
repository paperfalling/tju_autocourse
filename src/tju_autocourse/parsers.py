import json
import re


def _normalize_json_like(text: str) -> str:
    json_text = text.replace("'", '"')
    json_text = json_text.replace("\t", "")
    json_text = json_text.replace("\n", "")
    json_text = re.sub(r"([a-zA-Z]+)(?=:)", r'"\1"', json_text)
    return json_text


def parse_status_text(resp_text: str) -> dict:
    match = re.search(r"{.*}", resp_text)
    if match is None:
        raise ValueError("未找到有效的JSON内容")
    try:
        return json.loads(_normalize_json_like(match.group()))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON 解析错误") from exc


def parse_courses_text(resp_text: str) -> list[dict]:
    match = re.search(r"\[.*\]", resp_text)
    if match is None:
        raise ValueError("未找到有效的JSON内容")
    try:
        data = json.loads(_normalize_json_like(match.group()))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON 解析错误") from exc

    courses_info = []
    for course_info in data:
        course_info["arrangement"] = [
            (
                int(item["weekState"], base=2),
                item["weekDay"],
                item["startUnit"],
                item["endUnit"],
            )
            for item in course_info["arrangeInfo"]
        ]
        courses_info.append(
            {
                "id": str(course_info["id"]),
                "no": str(course_info["no"]),
                "name": str(course_info["name"]),
                "arrangement": course_info["arrangement"],
                "code": str(course_info["code"]),
            }
        )
    return courses_info
