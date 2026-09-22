"""Sequential scheduling and response policies, independent of HTTP and clocks."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from loguru import logger

from .config import SelectionPolicy, TargetConfig
from .domain import Action, Capacity, Course, SelectionResult


def decide(
    result: SelectionResult, policy: SelectionPolicy, retries: Counter
) -> Action:
    """Consume a per-candidate, per-response budget when scheduling a retry."""
    if result is SelectionResult.SUCCESS:
        raise ValueError("success is accounted for by the scheduler")
    rule = getattr(policy, result.value)
    if rule.action != "retry":
        return Action(rule.action)
    if rule.max_retries is not None and retries[result] >= rule.max_retries:
        return Action(rule.on_exhausted)
    retries[result] += 1
    return Action.RETRY


@dataclass
class ScheduleReport:
    succeeded: list[Course] = field(default_factory=list)
    unknown: list[Course] = field(default_factory=list)
    stopped: bool = False


class Scheduler:
    def __init__(
        self,
        courses: list[Course],
        capacities: dict[str, Capacity],
        selected: list[Course],
        targets: list[TargetConfig],
        *,
        skip_pre: bool,
        name: str = "user",
    ):
        self.courses = {course.no: course for course in courses}
        self.capacities = capacities
        self.selected = list(selected)
        self.targets = targets
        self.skip_pre = skip_pre
        self.name = name

    def eligible(self, course: Course) -> bool:
        if any(course.conflicts(selected) for selected in self.selected):
            return False
        if not self.skip_pre:
            capacity = self.capacities.get(course.id)
            if capacity is None or capacity.full:
                return False
        return True

    def run(self, select: Callable[[Course], SelectionResult]) -> ScheduleReport:
        report = ScheduleReport()
        for group in self.targets:
            succeeded = 0
            for number in group.courses:
                if 0 <= group.limit <= succeeded:
                    break
                course = self.courses.get(number)
                if course is None or not self.eligible(course):
                    logger.info(
                        "{} [{}] 跳过候选 {}（不存在或本地检查未通过）",
                        self.name,
                        group.group_name,
                        number,
                    )
                    continue
                retries = Counter()
                while True:
                    result = select(course)
                    logger.info(
                        "{} [{}] {}: {}",
                        self.name,
                        group.group_name,
                        course.no,
                        result.value,
                    )
                    if result is SelectionResult.SUCCESS:
                        succeeded += 1
                        self.selected.append(course)
                        report.succeeded.append(course)
                        break
                    if (
                        result is SelectionResult.UNKNOWN
                        and course not in report.unknown
                    ):
                        report.unknown.append(course)
                    action = decide(result, group.selection_policy, retries)
                    if action is Action.STOP:
                        report.stopped = True
                        return report
                    if action is Action.SKIP:
                        break
        return report
