"""Save complete course and capacity snapshots for each configured user."""

from tju_autocourse.api import fetch_courses
from tju_autocourse.commands import cli

if __name__ == "__main__":
    raise SystemExit(cli(fetch_courses))
