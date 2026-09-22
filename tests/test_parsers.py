import pytest

from tju_autocourse.errors import ProtocolError
from tju_autocourse.parsers import (
    parse_courses_text,
    parse_done_text,
    parse_ids_text,
    parse_name,
    parse_profiles,
    parse_status_text,
)

from .conftest import COURSES, EMPTY_TABLE, HOME


def test_course_parser_preserves_quoted_punctuation_and_leading_zeroes():
    text = COURSES.replace("name:'数学'", '''name:"O'Reilly: 数学"''')
    course = parse_courses_text(text)[0]
    assert course.name == "O'Reilly: 数学" and course.no == "00001"
    assert course.arrangement[0].weeks == 3
    assert parse_courses_text("let unused=[];\n" + text) == [course]


def test_capacity_and_empty_data():
    assert (
        parse_status_text("prefix {'1':{sc:1,lc:2,unplan:'否'}} suffix")["1"].limit == 2
    )
    assert parse_status_text("{}") == {}
    assert parse_courses_text("[]") == []


def test_selected_grid_accepts_changing_ids_and_rejects_error_pages():
    assert parse_done_text(EMPTY_TABLE) == []
    assert parse_done_text(
        '<tbody id="grid987_data"><tr><td>1</td><td><a>00001</a></td></tr></tbody>'
    ) == ["00001"]
    with pytest.raises(ProtocolError):
        parse_done_text("server unavailable")
    assert parse_ids_text("bg.form.addInput(form, 'ids', '42');") == "42"


def test_initialization_parsers():
    assert parse_name(HOME) == "测试用户"
    page = '<div><h2>轮次一</h2><form><input name="electionProfile.id" value="123"></form></div><div><h2>轮次二</h2><script>url="x?electionProfile.id=456"</script></div>'
    assert parse_profiles(page) == [(123, "轮次一"), (456, "轮次二")]


@pytest.mark.parametrize(
    "parser",
    [
        parse_courses_text,
        parse_status_text,
        parse_ids_text,
        parse_done_text,
        parse_name,
        parse_profiles,
    ],
)
def test_invalid_data_fails_loudly(parser):
    with pytest.raises(ProtocolError):
        parser("not the expected page")
