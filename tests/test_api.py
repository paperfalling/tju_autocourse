import threading

from tju_autocourse import api


def test_work_runs_each_user_in_an_independent_worker_thread(monkeypatch):
    barrier = threading.Barrier(2)

    class FakeUser:
        def __init__(self, name):
            self.name = name
            self.thread_name = None

        def run(self):
            self.thread_name = threading.current_thread().name
            barrier.wait()

    users = [FakeUser("a"), FakeUser("b")]
    monkeypatch.setattr(api, "get_config", lambda _path: {"meta": {}, "users": []})
    monkeypatch.setattr(api, "set_config_meta", lambda _meta: None)
    monkeypatch.setattr(api, "create_users", lambda _configs: users)

    api._work("config.yaml")

    assert all(user.thread_name for user in users)
    assert users[0].thread_name != users[1].thread_name


def test_work_continues_when_one_user_fails(monkeypatch):
    called = []

    class FakeUser:
        def __init__(self, name, fails=False):
            self.name = name
            self.fails = fails

        def run(self):
            called.append(self.name)
            if self.fails:
                raise RuntimeError("worker failed")

    users = [FakeUser("bad", True), FakeUser("good")]
    monkeypatch.setattr(api, "get_config", lambda _path: {"meta": {}, "users": []})
    monkeypatch.setattr(api, "set_config_meta", lambda _meta: None)
    monkeypatch.setattr(api, "create_users", lambda _configs: users)

    api._work("config.yaml")

    assert sorted(called) == ["bad", "good"]
