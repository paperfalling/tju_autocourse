import datetime
import threading

import pytest
import yaml

from tju_autocourse import api
from tju_autocourse.commands import check_courses, initialize
from tju_autocourse.domain import Capacity
from tju_autocourse.domain import SelectionResult as R
from tju_autocourse.errors import (
    AuthenticationError,
    Cancelled,
    ProtocolError,
    TransportError,
)
from tju_autocourse.storage import load_snapshot, save_snapshot
from tju_autocourse.transport import Clock
from tju_autocourse.user import User

from .conftest import FakeClock


class Gateway:
    def __init__(
        self, courses=(), *, capacities=None, selected=(), results=(), failure=None
    ):
        self.courses = list(courses)
        self.capacities = capacities or {}
        self.selected = list(selected)
        self.results = iter(results)
        self.failure = failure
        self.calls = []
        self.closed = False

    def __enter__(self):
        self.calls.append("open")
        return self

    def __exit__(self, *_exc):
        self.closed = True

    def get_course_info(self):
        self.calls.append("courses")
        if self.failure == "courses":
            raise TransportError("query failed")
        return self.courses

    def get_course_status(self):
        self.calls.append("capacity")
        if self.failure == "capacity":
            raise ProtocolError("query failed")
        return self.capacities

    def get_selected_courses(self, courses):
        self.calls.append("selected")
        if self.failure == "selected":
            raise ProtocolError("query failed")
        return self.selected

    def select_course(self, course_id):
        self.calls.append(("select", course_id))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def test_timeout_may_have_selected_but_no_confirmation_query(make_config, course):
    gateway = Gateway(
        [course(), course("00002")], results=[TransportError("timeout"), R.SUCCESS]
    )
    user = User(make_config(skipPre=True), client=gateway, clock=FakeClock())
    report = user.run()
    assert gateway.calls == [
        "open",
        "courses",
        "selected",
        ("select", "1"),
        ("select", "2"),
    ]
    assert len(report.succeeded) == len(report.unknown) == 1
    assert gateway.closed


@pytest.mark.parametrize("failure", ["courses", "capacity", "selected"])
def test_required_preparation_failure_stops_before_selection(
    make_config, course, failure
):
    gateway = Gateway([course()], failure=failure)
    with pytest.raises((TransportError, ProtocolError)):
        User(make_config(), client=gateway).run()
    assert not any(isinstance(c, tuple) for c in gateway.calls)
    assert gateway.closed


def test_snapshot_fetch_includes_capacity_even_with_skip_pre(
    make_config, course, tmp_path
):
    gateway = Gateway([course()], capacities={"1": Capacity(2, 3, "否")})
    User(make_config(skipPre=True), client=gateway).prepare(tmp_path)
    courses, capacities = load_snapshot(tmp_path, "tester")
    assert courses == [course()] and capacities == gateway.capacities
    assert "capacity" in gateway.calls and gateway.closed
    assert (tmp_path / "course_statu_tester.json").is_file()


def test_waits_until_target_time_without_real_sleep(make_config, course):
    clock = FakeClock()
    gateway = Gateway([course()], results=[R.SUCCESS])
    target = datetime.datetime.fromtimestamp(1.25)
    report = User(
        make_config(skipPre=True, startTime=target), client=gateway, clock=clock
    ).run()
    assert clock.now == pytest.approx(1.25)
    assert len(report.succeeded) == 1


def test_worker_threads_are_independent_and_failure_isolated():
    barrier = threading.Barrier(2)
    seen = []

    class Worker:
        def __init__(self, name):
            self.name = name

        def run(self):
            seen.append((self.name, threading.get_ident()))
            barrier.wait(timeout=5)
            if self.name == "bad":
                raise AuthenticationError("expired")

    assert api.run_users([Worker("bad"), Worker("good")]) is False
    assert {name for name, _ in seen} == {"bad", "good"}
    assert len({identifier for _, identifier in seen}) == 2


def test_interrupt_notifies_workers_before_waiting_for_shutdown(monkeypatch):
    class Worker:
        name = "worker"

        def __init__(self):
            self.cancelled = threading.Event()

        def run(self):
            assert self.cancelled.wait(timeout=5)

        def cancel(self):
            self.cancelled.set()

    worker = Worker()

    def interrupted(_futures):
        raise KeyboardInterrupt

    monkeypatch.setattr(api, "as_completed", interrupted)
    with pytest.raises(KeyboardInterrupt):
        api.run_users([worker])
    assert worker.cancelled.is_set()


def test_cancel_interrupts_wait_and_closes_user(make_config, course):
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        Clock(event).sleep(100)
    gateway = Gateway([course()])
    user = User(make_config(skipPre=True), client=gateway, clock=FakeClock())
    user.cancel()
    with pytest.raises(Cancelled):
        user.run()
    assert gateway.closed


def raw_user():
    return {"auth": {"type": "cookie", "cookie": "private-cookie"}, "targets": []}


def write_yaml(path, raw):
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")


def test_init_failure_preserves_original_file(tmp_path):
    path = tmp_path / "config.yaml"
    write_yaml(path, {"users": [raw_user()]})
    before = path.read_bytes()

    class Failed:
        def __enter__(self):
            raise AuthenticationError("expired")

        def __exit__(self, *_exc):
            pass

    assert (
        initialize(path, client_factory=lambda _: Failed(), output=lambda _: None)
        is False
    )
    assert path.read_bytes() == before


def test_init_uses_one_session_and_only_writes_successful_fields(tmp_path):
    path = tmp_path / "config.yaml"
    write_yaml(path, {"users": [raw_user()]})
    calls = []

    class Metadata:
        def __enter__(self):
            calls.append("open")
            return self

        def __exit__(self, *_exc):
            calls.append("close")

        def get_name(self):
            return "student"

        def get_semester_id(self):
            raise ProtocolError("unavailable")

        def get_profiles(self):
            return [(4, "first"), (5, "second")]

    assert (
        initialize(
            path,
            client_factory=lambda _: Metadata(),
            ask=lambda _: "2",
            output=lambda _: None,
        )
        is False
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    user = raw["users"][0]
    assert user["name"] == "student" and user["profileId"] == 5
    assert "semesterId" not in user
    assert user["auth"] == raw_user()["auth"]
    assert calls == ["open", "close"]


def test_init_creates_template_without_contacting_network(tmp_path):
    path, template = tmp_path / "config.yaml", tmp_path / "template.yaml"
    write_yaml(template, {"users": [raw_user()]})
    assert initialize(
        path,
        template_path=template,
        client_factory=lambda _: pytest.fail("unexpected network"),
        output=lambda _: None,
    )
    assert path.read_bytes() == template.read_bytes()


def test_check_courses_uses_existing_snapshot_format(tmp_path, course):
    path = tmp_path / "config.yaml"
    write_yaml(
        path,
        {
            "users": [
                raw_user()
                | {
                    "name": "tester",
                    "targets": [
                        {"group_name": "g", "limit": 1, "courses": ["00001", "99999"]}
                    ],
                }
            ]
        },
    )
    save_snapshot(tmp_path, "tester", [course()], {"1": Capacity(2, 3, "否")})
    lines = []
    check_courses(path, tmp_path, output=lines.append)
    assert any("00001" in line for line in lines)
    assert any("99999" in line and "未找到" in line for line in lines)
    assert any("2/3" in line for line in lines)


def test_initialize_preserves_course_identifiers_for_yaml_12_readers(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """users:
- auth: {type: cookie, cookie: fixture-only}
  profileId: 1
  semesterId: 2
  targets:
  - group_name: g
    limit: 1
    courses: ["02058", "02059", "06306"]
""",
        encoding="utf-8",
    )

    class Metadata:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            pass

        def get_name(self):
            return "tester"

    assert initialize(path, client_factory=lambda _: Metadata(), output=lambda _: None)
    root = yaml.compose(path.read_text(encoding="utf-8"))

    def field(node, name):
        return next(value for key, value in node.value if key.value == name)

    scalars = field(
        field(field(root, "users").value[0], "targets").value[0], "courses"
    ).value
    assert [node.value for node in scalars] == ["02058", "02059", "06306"]
    # Quoted scalars are strings in both YAML 1.1 and 1.2, including editor tooling.
    assert all(node.style in {"'", '"'} for node in scalars)


def test_course_fetch_never_rewrites_config(tmp_path, monkeypatch, course):
    path = tmp_path / "config.yaml"
    path.write_text(
        """# Preserve comments and quoted identifiers exactly.
users:
- name: tester
  auth: {type: cookie, cookie: fixture-only}
  profileId: 1
  semesterId: 2
  targets:
  - group_name: g
    limit: 1
    courses: ["02058", "02059", "06306"]
""",
        encoding="utf-8",
    )
    before = path.read_bytes()
    monkeypatch.setattr(api, "init_logger", lambda: None)

    def create(config):
        gateway = Gateway([course("02058")], capacities={"2058": Capacity(1, 2)})
        return User(config, client=gateway)

    monkeypatch.setattr(api, "create_user", create)
    assert api.fetch_courses(str(path), str(tmp_path / "data"))
    assert path.read_bytes() == before
    courses, _ = load_snapshot(tmp_path / "data", "tester")
    assert courses[0].no == "02058"
