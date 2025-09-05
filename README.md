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
        "semesterId": 116
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
> Fill in the **course number** instead of the course code
