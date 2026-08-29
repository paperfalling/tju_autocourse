# TJU AutoCourse

[中文说明](./README_zh.md)

TJU course-selection automation using the university CAS login and EAMS APIs. Each configured user owns an independent `requests.Session`; users run in separate worker threads.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

## Configure

Copy `config.template.yaml` to `config.yaml`, then fill in credentials and targets:

```yaml
meta:
  domain: classes.tju.edu.cn
  startTime: 2026-09-01T08:00:00
  request_interval: 0.5

users:
  - name: user1
    username: "your student ID"
    password: "your password"
    targets:
      - group_name: required
        limit: 1
        courses: ["06488", "06491"]
```

`profileId` and `semesterId` can be filled automatically by the initialization tool. A legacy browser `cookie` may be used instead of `username` and `password`.

## Run

Recommended first run:

```bash
uv run ./scripts/init.py
uv run ./scripts/course_fetch.py
uv run ./scripts/check_course.py
uv run ./main.py
```

`init.py` logs in and fills missing user metadata. `course_fetch.py` saves course and availability snapshots under `data/`. `check_course.py` validates that configured course numbers exist and displays their schedules and availability.

For normal operation, keep `request_interval: 0.5` or higher. `startTime` is the moment selection attempts begin. After session expiry, credential users are re-authenticated up to `auth_retries` times; Cookie-only sessions cannot re-authenticate automatically. A `TOO_FAST` business response is retried up to `too_fast_retries` times with the configured interval. Set `skipPre: true` only when you intentionally want to skip the availability pre-check.

## Configuration

- `meta`: defaults shared by all users.
- `users`: independent credentials and targets; user values override `meta`.
- `targets`: ordered course groups.
- `limit`: successful selections allowed in a group; `-1` means unlimited and `0` skips the group.
- `courses`: course numbers in priority order, not course codes.
- `auth_retries`: re-login attempts after an authenticated request detects an expired session.
- `too_fast_retries`: retries after the server reports that requests arrived too quickly.

The application distinguishes authentication, transport, protocol, and business-result failures. A failed login stops that user before selection requests. Unknown selection results are confirmed through the selected-course query before the scheduler proceeds.

## Security

Never commit `config.yaml`, passwords, cookies, captcha images, or response bodies. Runtime logs are written to `logs/`; generated snapshots are written to `data/`.

## Tests

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

The test suite uses deterministic fake HTTP responses. Real TJU requests are only made when you run the application or an explicitly chosen helper.

## Disclaimer

For technical research and learning only. You are responsible for complying with TJU rules and applicable laws.
