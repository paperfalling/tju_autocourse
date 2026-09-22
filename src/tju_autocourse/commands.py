"""Reusable implementations for the existing auxiliary script entrypoints."""

from pathlib import Path

from .config import parse_config, read_config
from .errors import AuthenticationError, AutoCourseError
from .session import AuthenticatedEams
from .storage import load_snapshot, write_config


def _choose_profile(profiles, ask, output):
    if len(profiles) == 1:
        return profiles[0][0]
    for index, (profile_id, name) in enumerate(profiles, 1):
        output(f"{index}. {name} ({profile_id})")
    while True:
        choice = ask("请输入选课项目编号 (默认 1): ").strip() or "1"
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            return profiles[int(choice) - 1][0]
        output("输入无效，请重新输入")


def initialize(
    config_path="./config.yaml",
    *,
    template_path="./config.template.yaml",
    client_factory=AuthenticatedEams,
    ask=input,
    output=print,
) -> bool:
    path = Path(config_path)
    if not path.exists():
        path.write_text(
            Path(template_path).read_text(encoding="utf-8"), encoding="utf-8"
        )
        output("已创建配置文件，请填写 auth 后重新运行初始化工具")
        return True
    raw = read_config(path)
    config = parse_config(raw)
    changed, succeeded = False, True
    for user, original in zip(config.users, raw["users"], strict=True):
        try:
            with client_factory(user) as client:
                tasks = []
                if not original.get("name"):
                    tasks.append(("name", client.get_name))
                if not user.semesterId:
                    tasks.append(("semesterId", client.get_semester_id))
                if not user.profileId:
                    tasks.append(
                        (
                            "profileId",
                            lambda: _choose_profile(client.get_profiles(), ask, output),
                        )
                    )
                for field, query in tasks:
                    try:
                        value = query()
                        if not value:
                            raise AutoCourseError("未获得有效字段值")
                        original[field] = value
                        changed = True
                    except AuthenticationError as exc:
                        succeeded = False
                        output(f"{user.name}: 登录状态失效: {exc}")
                        break
                    except AutoCourseError as exc:
                        succeeded = False
                        output(f"{user.name}: {field} 补全失败: {exc}")
        except AutoCourseError as exc:
            succeeded = False
            output(f"{user.name}: 初始化失败: {exc}")
    if changed:
        # Revalidate discovered names and identifiers before writing any changes.
        parse_config(raw)
        write_config(path, raw)
        output("已保存成功获取的配置字段")
    return succeeded


def check_courses(config_path="./config.yaml", directory="./data", *, output=print):
    config = parse_config(read_config(config_path))
    output("正在检查选课计划；如需刷新快照，请先运行 scripts/course_fetch.py")
    for user in config.users:
        courses, capacities = load_snapshot(directory, user.name)
        indexed = {course.no: course for course in courses}
        output(f"用户 {user.name} 选课计划:")
        for group in user.targets:
            output(f"  组 {group.group_name} (限制: {group.limit}):")
            for number in group.courses:
                course = indexed.get(number)
                if course is None:
                    output(f"    课程序号 {number} 未找到课程信息")
                    continue
                output(f"    {course.name} ({course.no}) 课程代码: {course.code}")
                output(f"      课程安排: {course.to_record()['arrangement']}")
                capacity = capacities.get(course.id)
                output(
                    f"      余量: {capacity.selected}/{capacity.limit} 是否开放计划外: {capacity.unplan}"
                    if capacity
                    else "      课程状态信息未找到"
                )


def cli(command):
    try:
        return 1 if command() is False else 0
    except KeyboardInterrupt:
        print("已中止，正在关闭用户会话")
        return 130
    except (ValueError, AutoCourseError, OSError) as exc:
        # YAML and network layers already remove secrets; avoid OS exception paths.
        print(
            str(exc)
            if isinstance(exc, (AutoCourseError, ValueError))
            else "文件读写失败，请检查配置与快照路径"
        )
        return 1
