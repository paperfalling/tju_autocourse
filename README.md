# TJU AutoCourse

[中文](README_zh.md)

Automatic course selection for TJU EAMS, with browser Cookie and SSO credential authentication. Requires Python 3.13+ and uv. Each user runs in an independent worker thread with one synchronous `requests` session; requests for that user are serialized.

## Quick start

```powershell
uv sync
Copy-Item config.template.yaml config.yaml
# Fill in authentication and course targets.
uv run scripts/init.py
uv run scripts/course_fetch.py
uv run scripts/check_course.py
uv run main.py
```

Initialization discovers missing name, semester and election profile fields, prompting when several profiles are available. Only successfully discovered fields are written; failed users are preserved. When the configuration is absent, initialization only copies the template. Course fetching exports both course and capacity snapshots even with `skipPre: true`. Checking courses uses local snapshots without network requests.

The main program prepares course and selected-course data, and capacity data when prechecking is enabled. Required query failures stop that user. It then waits for `startTime` before submitting selections. Naive timestamps use the host's local timezone. Ctrl+C interrupts waits/retries and closes sessions after in-flight HTTP requests return or time out.

## Configuration and authentication

```yaml
meta:
  domain: classes.tju.edu.cn
  startTime: 2026-09-23T12:00:00
  skipPre: false
  selection_policy:
    not_open: retry
    too_fast: retry
    full: skip
    already_selected: skip
    unknown: skip

users:
  - name: user1
    auth:
      type: cookie
      cookie: "complete browser Cookie header"
    targets:
      - group_name: required
        limit: 1
        courses: ["06488", "06491"]
```

Use course numbers, not course codes. `scripts/init.py` fills in missing `profileId` and `semesterId`; remove `name` to discover it as well. User settings override `meta`, including explicit `false` values. Authentication belongs to each user, never to `meta`.

For SSO, replace the entire `auth` mapping:

```yaml
auth:
  type: sso
  username: "student ID"
  password: "password"
  retries: 2
```

Cookie credentials are imported into a cookie jar scoped to the EAMS host, allowing server updates. Expiry stops Cookie users. SSO initially allows `1 + retries` login attempts; each later authentication recovery permits at most `retries` re-logins. Recovery validates the new session, restores the election profile, then retries the original operation. A successful login alone does not reset the recovery budget. Set `retries: 0` to disable retries. One user's failure does not cancel other users.

SSO follows the TJU CAS flow, sending the concatenated username, password and login token to `https://learning.twt.edu.cn/enc`, and captcha images to that site's `/ocr` endpoint. These external helpers use a separate session from CAS/EAMS. Helper availability, captcha recognition and protocol changes can affect login.

Course numbers must be quoted strings. Configuration writes always quote them and preserve leading zeroes, preventing YAML 1.1/1.2 differences from turning `02058` into integer `2058`. Already-numeric values require explicit correction; the program does not guess missing zeroes. `course_fetch.py` never writes the configuration file.

## Scheduling and response policies

Groups and their candidate lists run in strict order. The next group starts only when the current group reaches its limit or exhausts its candidates. Completed groups are not revisited. `limit: -1` is unlimited, `0` skips the group, and positive limits count explicit successes during this run. Previously selected courses are used for conflict checks, not counted as new successes.

Time conflicts, duplicate course codes and missing course numbers are filtered locally. With prechecking enabled, a full or missing capacity snapshot also filters the candidate before any response policy applies. `skipPre: true` bypasses only capacity checks, retaining conflict checks, limits and pacing. Capacity data can become stale after enrollment opens; users explicitly choose when to bypass it. There is no automatic time-based switch. To retry a course already full in the snapshot, enable `skipPre`.

| Response | Default action | Meaning |
| --- | --- | --- |
| `not_open` | `retry` | Keep requesting the current candidate |
| `too_fast` | `retry` | Retry the current candidate after pacing |
| `full` | `skip` | Move to the next candidate |
| `already_selected` | `skip` | Move on without incrementing success counts |
| `unknown` | `skip` | Timeout, gateway failure or unrecognized response; record and move on |

Successful selection always updates progress and selected courses. Authentication failures always use the authentication module. Neither is a configurable business policy. Under the system's operating assumption, “not open” affects the entire election profile, so switching courses would not help. The parser cannot distinguish “not started” from “already ended”; unlimited retries may require manual cancellation or a finite rule.

Actions are `retry`, `skip` and `stop`; `stop` ends the entire user's run. Finite retries:

```yaml
selection_policy:
  full:
    action: retry
    max_retries: 3
    on_exhausted: skip
```

`max_retries` counts additional retries after the initial attempt; omission means unlimited, and zero means no retry. For finite rules, `on_exhausted` defaults to `skip` and may be `stop`. Invalid actions, negative budgets and inapplicable options are rejected at startup.

Policies inherit through `meta → user → target group`. Each response rule is replaced as a whole; unspecified responses inherit. Therefore `full: retry` at group level means unlimited retries, even if an ancestor has a finite budget. Budgets accumulate separately per response and candidate; alternating responses and SSO recovery do not reset them. A new candidate gets fresh budgets.

All actual EAMS request starts for one user are separated by at least **0.55 seconds**, including composite queries, failures and replacement sessions. Users have independent timers. CAS/helper calls have timeouts but do not use EAMS pacing. The interval does not guarantee the server will never report “too fast.”

By default, unknown selection outcomes are **not queried for confirmation**. Only explicit success is counted, and the next candidate can be attempted even if the server actually accepted the previous request. Actual enrollment may therefore exceed the client's count or group limit. This is the agreed throughput-oriented behavior; check the real timetable afterward.

## Architecture and validation

See the [architecture walkthrough (Chinese)](docs/architecture.md) for module responsibilities, request flow, state ownership and change locations.

Configuration resolves inheritance; authentication/session modules own identity and lifecycle; EAMS operations return typed values; the pure scheduler owns progress and policy budgets; application entrypoints own time and per-user concurrency. Logging is initialized only by entrypoints. Invalid selected-course pages never become empty timetables. Snapshots retain `data/course_info_<name>.json` and `data/course_statu_<name>.json`; logs go to `logs/`.

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
```

Tests use scripted HTTP, the real Requests cookie jar, virtual clocks and temporary files, with no school network access. Both authentication modes additionally require live read-only validation with valid credentials: login, profile initialization and course queries. `scripts/course_fetch.py` performs those operations without submitting a course selection. Passing offline tests does not establish live SSO compatibility.

Do not commit credentials, local configuration or raw responses. This project is for technical research and learning; users are responsible for following university rules.
