# TJU AutoCourse

[English](./README.md)

基于天津大学 CAS 登录和 EAMS 接口的自动选课工具。每个用户拥有独立的 `requests.Session`，多个用户在独立 worker 线程中运行。

## 环境要求

- Python 3.13 及以上
- [uv](https://docs.astral.sh/uv/)

## 安装

```bash
uv sync
```

## 配置

复制 `config.template.yaml` 为 `config.yaml`，填写账密和课程目标：

```yaml
meta:
  domain: classes.tju.edu.cn
  startTime: 2026-09-01T08:00:00
  request_interval: 0.5

users:
  - name: user1
    username: "学号"
    password: "密码"
    targets:
      - group_name: 必选
        limit: 1
        courses: ["06488", "06491"]
```

`profileId` 和 `semesterId` 可由初始化工具自动填写。也可以使用从浏览器复制的 `cookie`，此时不填写 `username` 和 `password`。

## 运行

首次运行建议按以下顺序执行：

```bash
uv run ./scripts/init.py
uv run ./scripts/course_fetch.py
uv run ./scripts/check_course.py
uv run ./main.py
```

`init.py` 会登录并补全用户信息；`course_fetch.py` 将课程和余量快照保存到 `data/`；`check_course.py` 检查配置的课程号是否存在，并显示课程安排和余量。

正常运行建议保持 `request_interval: 0.5` 或更高。`startTime` 是开始尝试选课的时间。会话失效后，账密用户最多重新登录 `auth_retries` 次；仅 Cookie 模式没有账密，无法自动重新登录。服务器返回 `TOO_FAST`（点击过快）时，会按配置间隔最多重试 `too_fast_retries` 次。只有明确需要跳过余量预检查时才设置 `skipPre: true`。

## 配置说明

- `meta`：所有用户共享的默认配置。
- `users`：独立的认证信息和选课目标，用户字段会覆盖 `meta`。
- `targets`：按顺序执行的课程组。
- `limit`：课程组允许成功选中的数量；`-1` 表示不限，`0` 表示跳过该组。
- `courses`：按优先级排列的课程号，不是课程代码。
- `auth_retries`：检测到会话失效后允许重新登录的次数。
- `too_fast_retries`：服务器返回“点击过快”后允许重试的次数。

程序区分认证、网络传输、协议和业务结果错误。登录失败会在发送选课请求前停止该用户；选课结果未知时会先查询已选课程，再决定调度器是否继续。

## 安全

不要提交 `config.yaml`、密码、Cookie、验证码图片或响应正文。运行日志写入 `logs/`，课程快照写入 `data/`。

## 测试

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

测试使用确定性的假 HTTP 响应。只有运行程序或明确选择的辅助工具才会访问真实 TJU 服务。

## 免责声明

本项目仅用于技术研究和学习。使用者应自行遵守天津大学相关规定及适用法律。
