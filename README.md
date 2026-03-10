# TJU AutoCourse

[**English**](./README.md) | [**中文**](./README_zh.md)

![Python Version](https://img.shields.io/badge/python-%3E%3D3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

TJU AutoCourse is an automatic course selection tool designed for Tianjin University (TJU). It helps you automate the process of selecting courses with asynchronous requests for high efficiency.

## Features

- **Asynchronous Execution**: Built with `aiohttp` for fast and concurrent course selection operations.
- **Flexible Configuration**: Supports global settings with user-level overrides via `config.yaml`.
- **Multi-user Support**: Can handle multiple users and distinct course targets simultaneously.
- **Helper Scripts**: Includes utility scripts to fetch all course info, check course capacities, and validate your configuration before the actual selection begins.

## Prerequisites

- [Python >= 3.13](https://www.python.org/downloads/)
- [uv](https://github.com/astral-sh/uv) (An extremely fast Python package installer and resolver)

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/paperfalling/tju_autocourse.git
   cd tju_autocourse
   ```

2. Sync the dependencies and internal package using `uv`:

   ```bash
   uv sync
   ```

## Configuration

Duplicate or create your `config.yaml` in the project root directory. Here is an example:

```yaml
meta:
  domain: "classes.tju.edu.cn"
  profileId: 3820
  semesterId: 116
  startTime: "1970-01-01T08:00:00"
  skipPre: false

users:
  - name: "your name (any)"
    cookie: "your cookie"
    targets:
      - group_name: "pe"
        limit: 1
        courses:
          - "06488"
          - "06491"
      - group_name: "ele"
        limit: 2
        courses:
          - "06236"
          - "06233"
```

> [!NOTE]
>
> 1. You must fill in the **course number (class ID)** instead of the course code.
> 2. Configuration keys defined in `meta` can be **overridden** in individual user configurations.
> 3. `domain`: The teaching system domain name, usually `classes.tju.edu.cn`.
> 4. `profileId` & `semesterId`: Can be found by inspecting the network requests (XHR/Fetch) when accessing the university's course selection page.
> 5. `startTime`: The exact time when course selection starts, formatted in ISO 8601 constraint. The script will wait until this time to start.
> 6. `skipPre`: If `true`, the program will bypass querying the course capacity/status and try to select courses directly.

## Usage

### Main Process

After configuring the `config.yaml`, run the main automated course selection script:

```bash
uv run ./main.py
```

### Helper Scripts

We provide several utility scripts located in the `scripts/` directory to help you prepare.

- **Fetch Course Information**
  Queries all available course information and saves it to `./data/course_info.json`.

  ```bash
  uv run ./scripts/course_info.py
  ```

- **Fetch Course Status**
  Queries the real-time capacity and selection status of courses and saves it to `./data/course_statu.json`.

  ```bash
  uv run ./scripts/course_statu.py
  ```

- **Validate Configuration**
  Checks all the exact courses listed in your `config.yaml` to ensure the course numbers are correct. Remember to fetch the info and status first.

  ```bash
  uv run ./scripts/course_info.py
  uv run ./scripts/course_statu.py
  uv run ./scripts/check_course.py
  ```

## Disclaimer

This tool is intended for personal study and research purposes only. The user assumes all responsibilities and risks associated with its use. Please comply with the university's rules and regulations regarding course selection.
