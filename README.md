# TJU AutoCourse

## Quick Start

Completing configuration (create and fill in `config.json`)

Then run the following command

```shell
uv sync
uv run ./main.py
```

## Config

### config.json

for example

```json
{
    "meta": {
        "domain": "classes.tju.edu.cn",
        "profileId": 3820,
        "semesterId": 116,
        "startTime": "1970-01-01T08:00:00",
        "skipPre": false
    },
    "users": [
        {
            "name": "your name (any)",
            "cookie": "your cookie",
            "tags_sort_limit": {
                "pe": 1,
                "ele": 2,
                "eng": 2,
                "req": -1
            },
            "courses": {
                "pe": ["06488", "06491"],
                "ele": ["06236", "06233"],
                "eng": [],
                "req": []
            }
        }
    ]
}
```

> [!NOTE]
>
> 1. Fill in the **course number** instead of the course code
> 2. The configuration in meta can be **overridden** in personal configuration

- `domain`: The domain name of the teaching system, usually `classes.tju.edu.cn`
- `profileId`: The profile ID of the user, can be found by inspecting the network requests when accessing the course selection page
- `semesterId`: The semester ID, can be found by inspecting the network requests when accessing the course selection page
- `startTime`: The earliest time when the course selection starts, in ISO 8601 format
- `skipPre`: Whether to skip the querying of course selection status, if true, the program will not check if the course selection is full and if the course exists

## Scripts

### course_info.py

A script to query all the course information and save in `./data/course_info.json`

```shell
uv run ./scripts/course_info.py
```

### course_statu.py

A script to query the course selection status and save in `./data/course_statu.json`

```shell
uv run ./scripts/course_statu.py
```

### check_course.py

A script to check all the courses in `config.json` for details to check the correctness of the course number in your configuration

```shell
uv run ./scripts/course_info.py
uv run ./scripts/course_statu.py
uv run ./scripts/check_course.py
```
