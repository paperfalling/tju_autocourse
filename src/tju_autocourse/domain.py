"""Values shared by parsing, scheduling and snapshot storage."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Meeting:
    weeks: int
    day: int
    start: int
    end: int

    def overlaps(self, other: "Meeting") -> bool:
        return (
            bool(self.weeks & other.weeks)
            and self.day == other.day
            and max(self.start, other.start) <= min(self.end, other.end)
        )


@dataclass(frozen=True)
class Course:
    id: str
    no: str
    name: str
    code: str
    arrangement: tuple[Meeting, ...]

    def conflicts(self, other: "Course") -> bool:
        return self.code == other.code or any(
            a.overlaps(b) for a in self.arrangement for b in other.arrangement
        )

    def to_record(self) -> dict:
        return {
            "id": self.id,
            "no": self.no,
            "name": self.name,
            "code": self.code,
            "arrangement": [[m.weeks, m.day, m.start, m.end] for m in self.arrangement],
        }

    @classmethod
    def from_record(cls, record: dict) -> "Course":
        return cls(
            str(record["id"]),
            str(record["no"]),
            str(record["name"]),
            str(record["code"]),
            tuple(Meeting(*m) for m in record["arrangement"]),
        )


@dataclass(frozen=True)
class Capacity:
    selected: int
    limit: int
    unplan: str = "未知"

    @property
    def full(self) -> bool:
        return self.selected >= self.limit

    def to_record(self) -> dict:
        return {"sc": self.selected, "lc": self.limit, "unplan": self.unplan}


class SelectionResult(StrEnum):
    SUCCESS = "success"
    NOT_OPEN = "not_open"
    TOO_FAST = "too_fast"
    FULL = "full"
    ALREADY_SELECTED = "already_selected"
    UNKNOWN = "unknown"


class Action(StrEnum):
    RETRY = "retry"
    SKIP = "skip"
    STOP = "stop"
