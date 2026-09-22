"""Pure parsers for EAMS HTML and embedded JavaScript data (never eval)."""

import ast
import re

from lxml import etree, html

from .domain import Capacity, Course, Meeting, SelectionResult
from .errors import ProtocolError

_TOKENS = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b[A-Za-z_$][\w$]*\b""")


def _literal(text):
    def replace(match):
        token = match.group()
        if token.startswith(("'", '"')):
            return token
        if text[match.end() :].lstrip().startswith(":"):
            return repr(token)
        return {"true": "True", "false": "False", "null": "None"}.get(token, token)

    return ast.literal_eval(_TOKENS.sub(replace, text))


def _embedded(text, opening):
    closing = "]" if opening == "[" else "}"
    for start in (m.start() for m in re.finditer(re.escape(opening), text)):
        depth, quote, escaped = 0, None, False
        for index in range(start, len(text)):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    try:
                        yield _literal(text[start : index + 1])
                    except (ValueError, SyntaxError, TypeError, RecursionError):
                        pass
                    break


def parse_courses_text(text: str) -> list[Course]:
    empty = False
    for value in _embedded(text, "["):
        if value == []:
            empty = True
            continue
        if not isinstance(value, list) or not all(
            isinstance(c, dict)
            and {"id", "no", "name", "code", "arrangeInfo"} <= c.keys()
            for c in value
        ):
            continue
        try:
            return [
                Course(
                    str(c["id"]),
                    str(c["no"]),
                    str(c["name"]),
                    str(c["code"]),
                    tuple(
                        Meeting(
                            int(m["weekState"], 2),
                            int(m["weekDay"]),
                            int(m["startUnit"]),
                            int(m["endUnit"]),
                        )
                        for m in c["arrangeInfo"]
                    ),
                )
                for c in value
            ]
        except (ValueError, TypeError, KeyError):
            raise ProtocolError("课程安排数据无法解析") from None
    if empty:
        return []
    raise ProtocolError("未找到有效课程列表")


def parse_status_text(text: str) -> dict[str, Capacity]:
    empty = False
    for value in _embedded(text, "{"):
        if value == {}:
            empty = True
            continue
        if not isinstance(value, dict) or not all(
            isinstance(s, dict) and {"sc", "lc"} <= s.keys() for s in value.values()
        ):
            continue
        try:
            return {
                str(key): Capacity(
                    int(s["sc"]), int(s["lc"]), str(s.get("unplan", "未知"))
                )
                for key, s in value.items()
            }
        except (ValueError, TypeError):
            raise ProtocolError("课程余量数据无法解析") from None
    if empty:
        return {}
    raise ProtocolError("未找到有效课程余量")


def _tree(text):
    try:
        return html.fromstring(text)
    except (ValueError, etree.ParserError):
        raise ProtocolError("EAMS 页面无法解析") from None


def parse_ids_text(text: str) -> str:
    match = re.search(
        r"""bg\.form\.addInput\(\s*form\s*,\s*["']ids["']\s*,\s*["'](\d+)["']\s*\)""",
        text,
    )
    if not match:
        raise ProtocolError("未找到课表标识")
    return match[1]


def parse_done_text(text: str) -> list[str]:
    tree = _tree(text)
    grids = tree.xpath('//*[starts-with(@id,"grid") and contains(@id,"_data")]')
    if not grids:
        raise ProtocolError("未找到已选课程表，不能将异常页面当成空课表")
    return [
        str(number).strip()
        for grid in grids
        for number in grid.xpath(".//tr/td[2]/a/text()")
        if str(number).strip()
    ]


def parse_name(text: str) -> str:
    values = _tree(text).xpath('//*[@id="main-top"]/div/div/div/a/text()')
    if not values or not values[0].strip():
        raise ProtocolError("未找到用户名")
    return values[0].strip()


def parse_profiles(text: str) -> list[tuple[int, str]]:
    profiles = []
    for heading in _tree(text).xpath("//h2"):
        parent = heading.getparent()
        values = parent.xpath(
            './/input[@name="electionProfile.id" or @name="profileId"]/@value'
        )
        if not values:
            values = re.findall(
                r"electionProfile\.id[=\s]+(\d+)",
                " ".join(parent.xpath(".//script/text()")),
            )
        if not values:
            # Some EAMS versions omit the input name on the profile form.
            values = parent.xpath(".//form/input/@value")
        for value in values:
            if str(value).isdigit():
                profiles.append((int(value), heading.text_content().strip()))
                break
    if not profiles:
        raise ProtocolError("未找到可选轮次")
    return profiles


def parse_selection(text: str) -> SelectionResult:
    # Authentication and HTTP failures are classified before business text.
    for keyword, result in (
        ("过快", SelectionResult.TOO_FAST),
        ("不开放", SelectionResult.NOT_OPEN),
        ("未开始", SelectionResult.NOT_OPEN),
        ("已满", SelectionResult.FULL),
        ("选过", SelectionResult.ALREADY_SELECTED),
    ):
        if keyword in text:
            return result
    if "成功" in text and not any(
        word in text for word in ("不成功", "未成功", "失败")
    ):
        return SelectionResult.SUCCESS
    return SelectionResult.UNKNOWN
