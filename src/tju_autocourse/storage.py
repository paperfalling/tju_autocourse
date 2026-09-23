"""Configuration writes and course snapshots."""

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

import yaml

from .domain import Capacity, Course


class _CourseNumber(str):
    """Always a quoted YAML string, across YAML 1.1 and 1.2 readers."""


class _ConfigDumper(yaml.SafeDumper):
    pass


_ConfigDumper.add_representer(
    _CourseNumber,
    lambda dumper, value: dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style='"'
    ),
)


def write_config(path: str | Path, raw: dict):
    path = Path(path)
    serialized = deepcopy(raw)
    for user in serialized.get("users", []):
        for group in user.get("targets", []):
            numbers = group.get("courses", [])
            if any(not isinstance(number, str) for number in numbers):
                raise ValueError(
                    "课程序号必须是字符串；请检查丢失的前导零，不要使用数字类型"
                )
            group["courses"] = [_CourseNumber(number) for number in numbers]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
            yaml.dump(
                serialized,
                file,
                Dumper=_ConfigDumper,
                allow_unicode=True,
                sort_keys=False,
            )
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_snapshot(
    directory: str | Path,
    name: str,
    courses: list[Course],
    capacities: dict[str, Capacity],
):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"course_info_{name}.json").write_text(
        json.dumps([c.to_record() for c in courses], ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    (directory / f"course_statu_{name}.json").write_text(
        json.dumps(
            {key: value.to_record() for key, value in capacities.items()},
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


def load_snapshot(
    directory: str | Path, name: str
) -> tuple[list[Course], dict[str, Capacity]]:
    directory = Path(directory)
    courses = json.loads(
        (directory / f"course_info_{name}.json").read_text(encoding="utf-8")
    )
    statuses = json.loads(
        (directory / f"course_statu_{name}.json").read_text(encoding="utf-8")
    )
    return [Course.from_record(c) for c in courses], {
        str(key): Capacity(
            int(value["sc"]), int(value["lc"]), str(value.get("unplan", "未知"))
        )
        for key, value in statuses.items()
    }
