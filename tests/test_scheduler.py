from collections import Counter

import pytest

from tju_autocourse.config import SelectionPolicy
from tju_autocourse.domain import Action, Capacity
from tju_autocourse.domain import SelectionResult as R
from tju_autocourse.scheduler import Scheduler, decide


def run(config, courses, results, *, selected=(), capacities=None):
    calls = []
    responses = iter(results)

    def select(course):
        calls.append(course.no)
        return next(responses)

    scheduler = Scheduler(
        courses,
        capacities or {},
        list(selected),
        config.targets,
        skip_pre=config.skipPre,
    )
    report = scheduler.run(select)
    return calls, report


def test_strict_group_order_limits_and_success_conflicts(make_config, course):
    config = make_config(
        skipPre=True,
        targets=[
            {"group_name": "zero", "limit": 0, "courses": ["00009"]},
            {"group_name": "first", "limit": 1, "courses": ["00001", "00002", "00003"]},
            {
                "group_name": "second",
                "limit": -1,
                "courses": ["00003", "00004", "00005"],
            },
        ],
    )
    courses = [
        course("00001"),
        course("00002"),
        course("00003"),
        course("00004", day=2),
        course("00005", code="00002", day=3),
        course("00009"),
    ]
    calls, report = run(
        config, courses, [R.NOT_OPEN, R.TOO_FAST, R.FULL, R.SUCCESS, R.SUCCESS]
    )
    assert calls == ["00001", "00001", "00001", "00002", "00004"]
    assert [c.no for c in report.succeeded] == ["00002", "00004"]


def test_response_budgets_survive_alternation_and_reset_for_next_candidate(
    make_config, course
):
    config = make_config(
        skipPre=True, selection_policy={"full": {"action": "retry", "max_retries": 1}}
    )
    calls, report = run(
        config,
        [course(), course("00002")],
        [R.FULL, R.TOO_FAST, R.FULL, R.FULL, R.SUCCESS],
    )
    assert calls == ["00001", "00001", "00001", "00002", "00002"]
    assert [c.no for c in report.succeeded] == ["00002"]


def test_unknown_continues_without_counting_or_confirmation(make_config, course):
    config = make_config(skipPre=True)
    calls, report = run(config, [course(), course("00002")], [R.UNKNOWN, R.SUCCESS])
    assert calls == ["00001", "00002"]
    assert report.unknown == [course()]
    assert report.succeeded == [course("00002")]


@pytest.mark.parametrize(
    "rule,results",
    [
        ("stop", [R.FULL]),
        (
            {"action": "retry", "max_retries": 1, "on_exhausted": "stop"},
            [R.FULL, R.FULL],
        ),
    ],
)
def test_stop_stops_entire_user(make_config, course, rule, results):
    config = make_config(
        skipPre=True,
        selection_policy={"full": rule},
        targets=[
            {"group_name": "a", "limit": 1, "courses": ["00001"]},
            {"group_name": "b", "limit": 1, "courses": ["00002"]},
        ],
    )
    calls, report = run(config, [course(), course("00002")], results)
    assert calls == ["00001"] * len(results)
    assert report.stopped


def test_capacity_precheck_precedes_retry_policy_and_skip_only_bypasses_capacity(
    make_config, course
):
    config = make_config(selection_policy={"full": "retry"})
    calls, _ = run(
        config, [course(), course("00002")], [], capacities={"1": Capacity(10, 10)}
    )
    assert calls == []  # second candidate has missing capacity
    bypass = make_config(skipPre=True)
    calls, _ = run(
        bypass,
        [course(), course("00002", day=2)],
        [R.SUCCESS],
        selected=[course("00009")],
        capacities={"2": Capacity(10, 10)},
    )
    assert calls == ["00002"]


@pytest.mark.parametrize(
    "weeks,day,start,end,conflict",
    [(1, 1, 2, 3, True), (4, 1, 1, 2, False), (1, 2, 1, 2, False), (1, 1, 3, 4, False)],
)
def test_conflicts_include_week_mask_day_and_inclusive_units(
    course, weeks, day, start, end, conflict
):
    assert (
        course().conflicts(course("00002", weeks=weeks, day=day, start=start, end=end))
        is conflict
    )


@pytest.mark.parametrize("result", [R.FULL, R.ALREADY_SELECTED, R.UNKNOWN])
def test_default_skips_terminal_results(result):
    assert decide(result, SelectionPolicy(), Counter()) is Action.SKIP


def test_zero_budget_and_unlimited_retries():
    policy = SelectionPolicy.model_validate(
        {"full": {"action": "retry", "max_retries": 0}}
    )
    assert decide(R.FULL, policy, Counter()) is Action.SKIP
    counters = Counter()
    for _ in range(10):
        assert decide(R.NOT_OPEN, policy, counters) is Action.RETRY
