# TJU AutoCourse

[**English**](./README.md) | [**中文**](./README_zh.md)

![Python Version](https://img.shields.io/badge/python-%3E%3D3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A high-concurrency asynchronous course selection tool designed for Tianjin University (TJU).

## Features

- **High-performance async architecture**: Built on `aiohttp` with fully asynchronous network requests.
- **Multi-account concurrency**: Supports running course selection tasks for multiple accounts in a single process.
- **Strategy-based course selection**: Supports custom course groups and selection limits to avoid duplicate selections and timetable conflicts.
- **Automation helpers**: Includes ready-to-use scripts for environment warm-up, data fetching, and configuration validation.

## Prerequisites

- [python](https://www.python.org/downloads/) >= 3.13
- [uv](https://github.com/astral-sh/uv)

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/paperfalling/tju_autocourse.git
   cd tju_autocourse
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   ```

3. **Initialize the configuration**:

   Create `config.yaml` in the project root with reference to `config.template.yaml`. Global settings under `meta` can be inherited and overridden by per-user settings under `users`:

   ```yaml
   meta:
     domain: classes.tju.edu.cn
     profileId: 3820
     semesterId: 116
     startTime: 1970-01-01T08:00:00 # scheduled trigger time
     skipPre: false                 # skip pre-checks to trade safety for speed

   users:
     - name: UserA                  # account label
       cookie: your cookie          # authentication credential from browser requests
       targets:
         - group_name: pe           # course group label
           limit: 1                 # maximum successful selections in this group
           courses:
             - "06488"              # candidate course numbers in priority order
             - "06491"
   ```

   > **Note**: The minimum required field is `cookie`. Then run `uv run ./scripts/init.py` to auto-fill `name`, `profileId`, and `semesterId`.

4. **Start the program**:

   ```bash
   uv run ./main.py
   ```

## Quick Start

Recommended minimal workflow for first-time use:

1. Run `uv sync` to install dependencies.
2. Create `config.yaml` in the project root and fill in at least the `cookie` for each user.
3. Run `uv run ./scripts/init.py` to auto-fill user information and selection parameters.
4. If you want to validate course numbers first, run the data fetch scripts and then run `uv run ./scripts/check_course.py`.
5. Confirm `startTime`, then run `uv run ./main.py`.

### Configuration Details

- **`meta` (global configuration)**: Provides default values inherited by users unless overridden in `users`.
  - `domain`: Course selection system domain. In most cases, keep the default value `classes.tju.edu.cn`.
  - `profileId` & `semesterId`: Selection round and semester identifiers. It is recommended to fetch them automatically with `init.py`.
  - `startTime`: Exact time when the program should begin sending selection requests. The program sleeps until this time.
  - `skipPre`: Set to `true` to skip the pre-run availability check.
- **`users` (user configuration)**: Lets you configure independent course selection tasks for multiple users. Fields defined here override the corresponding values in `meta`.
  - `name`: User label used only in logs and console output. If omitted, `init.py` can fill it automatically.
  - `cookie`: Full authentication credential copied from browser request headers.
- **`targets` (task groups)**: Used to group courses and limit how many can be selected, reducing duplicate selections and timetable conflicts.
  - `group_name`: Group label used for task grouping and logs.
  - `limit`: Maximum number of successful selections in the group. Once this limit is reached, remaining courses in the same group will be skipped. Set `-1` for no limit.
  - `courses`: Ordered list of desired course numbers. **Use the course number, not the course code.** Earlier items have higher priority.

## Helper Scripts

The project includes several validation and data-fetching scripts in the `scripts/` directory:

- **Initialize and auto-fill configuration**: `uv run ./scripts/init.py`
- **Fetch all course information for the current semester**: `uv run ./scripts/course_fetch.py`
- **Validate the local course list**: `uv run ./scripts/check_course.py` (run the previous scripts first to prepare the required data)

## FAQ

- **`uv run ./scripts/init.py` says it created `config.yaml` on first run**: This is expected. If the file does not exist, the script creates it from the template. Fill in the `cookie` field first, then run the script again.
- **`init.py` cannot fetch `name`, `profileId`, or `semesterId`**: The `cookie` is usually incomplete or expired. Log in to the course selection system again and copy the latest full `Cookie` header.
- **Course info or course status queries fail after startup**: Check whether `domain`, `profileId`, and `semesterId` are correct, and make sure the course selection system is reachable from your network.
- **Why does `skipPre` disable availability checks**: This is intentional. When set to `true`, the program skips the pre-run availability probe to save one round of requests, but it also loses the benefit of filtering based on current availability.
- **Where are the logs**: The program automatically creates a `logs/` directory in the project root and writes detailed runtime logs there.

## Disclaimer

This project is intended for technical research and learning purposes only. You are solely responsible for any risks or consequences arising from its use or from violating relevant university regulations.
