import pytest

from tju_autocourse.auth import AuthenticationError
from tju_autocourse.eams import (
    EamsClient,
    ProtocolError,
    SelectionState,
    TransportError,
)


class Response:
    def __init__(self, status=200, text=""):
        self.status = status
        self.text = text


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def client(session):
    return EamsClient(
        session, domain="classes.tju.edu.cn", profile_id=4419, semester_id=134
    )


def test_course_info_is_requested_and_parsed():
    session = Session(
        [
            Response(),
            Response(
                text="[{'id':1,'no':'10001','name':'线代','code':'MATH001','arrangeInfo':[{'weekState':'11','weekDay':1,'startUnit':1,'endUnit':2}]}]"
            ),
        ]
    )
    result = client(session).get_course_info()
    assert result[0]["no"] == "10001"
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["data"] == {"electionProfile.id": 4419}
    assert session.calls[1][2]["params"] == {"profileId": 4419}


def test_select_course_returns_typed_business_result():
    session = Session([Response(text="选课已满")])
    result = client(session).select_course("course-1")
    assert result.state is SelectionState.FULL
    assert result.succeeded is False


@pytest.mark.parametrize(
    "text,state",
    [
        ("\u6210\u529f", SelectionState.SUCCESS),
        ("\u8fc7\u5feb", SelectionState.TOO_FAST),
        ("\u4e0d\u5f00\u653e", SelectionState.NOT_OPEN),
        ("\u5df2\u6ee1", SelectionState.FULL),
        ("\u9009\u8fc7", SelectionState.ALREADY_SELECTED),
        ("unrecognized response", SelectionState.UNKNOWN),
    ],
)
def test_select_course_classifies_each_business_state(text, state):
    result = client(Session([Response(text=text)])).select_course("course-1")
    assert result.state is state
    assert result.succeeded is (state is SelectionState.SUCCESS)


def test_selected_courses_are_parsed_and_matched_to_course_info():
    session = Session(
        [
            Response(text='bg.form.addInput(form,"ids","42");'),
            Response(
                text=(
                    '<table><tbody id="grid12042826911_data">'
                    "<tr><td>x</td><td><a>10001</a></td></tr>"
                    "</tbody></table>"
                )
            ),
        ]
    )
    courses = [{"id": "c1", "no": "10001"}, {"id": "c2", "no": "10002"}]

    result = client(session).get_selected_courses(courses)

    assert result == [courses[0]]
    assert session.calls[1][2]["data"]["ids"] == "42"


@pytest.mark.parametrize("text", ["", "not-a-table"])
def test_selected_course_table_shape_errors_are_protocol_errors(text):
    session = Session(
        [
            Response(text='bg.form.addInput(form,"ids","42");'),
            Response(text=text),
        ]
    )
    with pytest.raises(ProtocolError):
        client(session).get_selected_courses([])


@pytest.mark.parametrize(
    "status,error", [(500, ProtocolError), (401, AuthenticationError)]
)
def test_client_classifies_http_failures(status, error):
    with pytest.raises(error):
        client(Session([Response(status=status)])).get_course_status()


def test_client_classifies_transport_failures():
    class BrokenSession:
        def request(self, *_args, **_kwargs):
            raise TimeoutError("timed out")

    with pytest.raises(TransportError):
        client(BrokenSession()).get_course_info()
