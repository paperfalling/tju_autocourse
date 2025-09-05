# TJU AutoCourse

## how to use

see the example in the scripts directory

```shell
uv sync
uv run ./scripts/example.py
```

## config

- **config.json**

    for example

    ```json
    [
        {
            "name": "your name (any)",
            "cookie": "your cookie",
            "tags_sort_limit": {
                "pe": 1,
                "ele": 1,
                "eng": 2,
                "req": -1
            },
            "courses": {
                "pe": ["06488", "06491"],
                "ele": ["05289"],
                "eng": [],
                "req": []
            },
            "domain": "classes.tju.edu.cn",
            "profileId": 3820,
            "semesterId": 116
        }
    ]
    ```
