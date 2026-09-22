"""Inspect configured targets against local course snapshots (no network)."""

from tju_autocourse.commands import check_courses, cli

if __name__ == "__main__":
    raise SystemExit(cli(check_courses))
