# TJU AutoCourse

[**English**](./README.md) | [**中文**](./README_zh.md)

![Python Version](https://img.shields.io/badge/python-%3E%3D3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

TJU AutoCourse 是一款专为天津大学（TJU）设计的自动化抢课/选课工具。利用异步并发网络请求，帮助你极速且高效地完成选课流程。

## 特性

- **异步并发操作**：基于 `aiohttp` 构建，选课请求极速且高并发。
- **灵活的配置**：通过 `config.yaml` 提供全局设置，且支持在具体的个人配置中进行覆盖重写（Override）。
- **多用户及分组支持**：你可以同时为多个用户配置不同的选课目标组及限选数量。
- **辅助测试脚本**：内置了获取全校课程信息、余量状态以及拉取校验本地配置的多个小工具，确保在选课开始前一切就绪。

## 运行环境

- [Python >= 3.13](https://www.python.org/downloads/)
- [uv](https://github.com/astral-sh/uv) (极速无缝的 Python 项目与包管理工具)

## 安装部署

1. 克隆代码仓库：

   ```bash
   git clone https://github.com/paperfalling/tju_autocourse.git
   cd tju_autocourse
   ```

2. 使用 `uv` 安装并同步项目依赖：

   ```bash
   uv sync
   ```

## 配置说明

在项目根目录下配置 `config.yaml` 文件。以下是一个参考模板：

```yaml
meta:
  domain: "classes.tju.edu.cn"
  profileId: 3820
  semesterId: 116
  startTime: "1970-01-01T08:00:00"
  skipPre: false

users:
  - name: "你的名字（用作标识，任意填写即可）"
    cookie: "你的教学系统登录 cookie"
    targets:
      - group_name: "pe" # 体育课分组
        limit: 1 # 本组成功选上几门后停止
        courses:
          - "06488"
          - "06491"
      - group_name: "ele" # 选修课分组
        limit: 2
        courses:
          - "06236"
          - "06233"
```

> [!NOTE]
>
> 1. 务必填写**教学班号 (Course Number)** 而非单纯的课程代码，因为一个课程会对应多个教学班。
> 2. `meta` 中定义的所有全局配置参数，都可以被放入 `users` 的个人配置中针对某人**单独覆盖（Override）**。
> 3. `domain`: 选课系统的域名，通常就是 `classes.tju.edu.cn`。
> 4. `profileId` & `semesterId`: 可以通过在浏览器中登录选课页面，打开开发者工具(F12)的网络面板(Network)抓包来寻找。
> 5. `startTime`: 选课开放的具体时间点 (遵循 ISO 8601 标准)。启动主程序后它会精确地等待到该时间点再开始全速发包。
> 6. `skipPre`: 若置为 `true`，程序将直接跳过冗余的“课程容量与是否存在”的前置拉取验证，直接开始抢。在真正抢课的争分夺秒时刻比较有用。

## 使用方法

### 开始抢课

确认 `config.yaml` 配置无误后，启动主自动选课程序：

```bash
uv run ./main.py
```

### 辅助验证脚本

我们在 `scripts/` 目录下准备了几个功能脚本，帮助你进行选课前的调研和排偏：

- **获取全校课程信息**
  抓取本学期的全部课程详细情况并下载至本地(`./data/course_info.json`)。

  ```bash
  uv run ./scripts/course_info.py
  ```

- **获取课程状态与余量**
  抓取各门课目前的选课人数、名额状态等，并保存至(`./data/course_statu.json`)。

  ```bash
  uv run ./scripts/course_statu.py
  ```

- **预检本地配置**
  帮你检查 `config.yaml` 中所填的教学班号合法性，看看是否存在填错/拼写错误。建议执行前先拉取好上面两个数据。

  ```bash
  uv run ./scripts/course_info.py
  uv run ./scripts/course_statu.py
  uv run ./scripts/check_course.py
  ```

## 免责声明

本工具仅限于进行技术研究和编程学习交流使用。因使用此脚本进行选课或因违反学校教务规定而引起的一切风险、责任与不良后果，均由使用者本人全权承担。
