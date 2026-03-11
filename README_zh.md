# TJU AutoCourse

[**English**](./README.md) | [**中文**](./README_zh.md)

![Python Version](https://img.shields.io/badge/python-%3E%3D3.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

专为天津大学（TJU）设计的高并发异步自动化选课工具。

## 特性

- **异步高性能**：基于 `aiohttp` 的全异步网络请求框架。
- **多账号并发**：支持单实例多账号并发选课。
- **策略化选课**：支持自定义课程组与限选数量, 避免多选与时间冲突。
- **自动化辅助**：内置开箱即用的环境预热、数据查询级校验脚本。

## 环境依赖

- [python](https://www.python.org/downloads/) >= 3.13
- [uv](https://github.com/astral-sh/uv)

## 安装部署

1. **克隆仓库**：

   ```bash
   git clone https://github.com/paperfalling/tju_autocourse.git
   cd tju_autocourse
   ```

2. **安装依赖**：

   ```bash
   uv sync
   ```

3. **初始化配置**：

   可参考 `config.template.yaml` 在项目根目录创建 `config.yaml` 文件。支持全局参数 (`meta`) 与局部配置 (`users`) 的继承覆写：

   ```yaml
   meta:
     domain: classes.tju.edu.cn
     profileId: 3820
     semesterId: 116
     startTime: 1970-01-01T08:00:00 # 挂机执行触发时间
     skipPre: false                 # 开启时跳过余量探活以换取执行速度

   users:
     - name: UserA                  # 账号标识
       cookie: your cookie          # 身份凭证 (登录后抓包获取)
       targets:
         - group_name: pe           # 课程组标识
           limit: 1                 # 本组选中上限数
           courses:
             - "06488"              # 备选课程序号, 按优先级排序
             - "06491"
   ```

   > **注**：最少只需填写 `cookie`。随后执行 `uv run ./scripts/init.py`，即可自动补全 `name`、`profileId` 及 `semesterId`。

4. **启动程序**：

   ```bash
   uv run ./main.py
   ```

## 快速开始

适合首次使用的最短流程：

1. 执行 `uv sync` 安装依赖。
2. 在项目根目录创建 `config.yaml`，至少填写每个用户的 `cookie`。
3. 执行 `uv run ./scripts/init.py` 自动补全用户信息与选课参数。
4. 如需预检课程序号，先执行数据拉取脚本，再执行 `uv run ./scripts/check_course.py`。
5. 确认 `startTime` 后，执行 `uv run ./main.py` 开始运行。

### 配置详解

- **`meta` (全局配置)**: 提供默认参数, 若 `users` 中未指定则继承此处的配置。
  - `domain`: 选课系统域名，通常保持默认值 `classes.tju.edu.cn` 即可。
  - `profileId` & `semesterId`: 选课轮次与学期标识, 建议通过 `init.py` 脚本自动获取。
  - `startTime`: 系统开始选课的确切时间。程序启动后会休眠至该时间再发起高并发请求。
  - `skipPre`: 设为 `true` 可跳过选课前的余量检查。
- **`users` (用户配置)**: 允许为多用户独立配置选课任务。如果在单个 user 下定义键值, 将会覆写全局 `meta` 的配置。
  - `name`: 用户标识, 仅用于日志与控制台输出展示。若未填写, 可由 `init.py` 自动获取。
  - `cookie`: 用户的完整登录凭证, 可通过浏览器抓包获取。
- **`targets` (任务组)**: 用于分类并限制选课数量, 防止时间冲突或多选。
  - `group_name`: 课程组标识, 仅用于任务分组与日志输出。
  - `limit`: 该组内课程**最多**选中的数量。达到该数量后, 程序会停止尝试该组内的其他课程。若设为 `-1`, 表示该组不限数量。
  - `courses`: 意向课程列表。**注意：此处必须填写"课程序号", 而非"课程代码"。** 按列表顺序优先级进行尝试。

## 辅助工具

项目提供多项运行前校验与数据拉取脚本（位于 `scripts/` 目录）：

- **参数初始化与补全**：`uv run ./scripts/init.py`
- **拉取本学期全部课程信息**：`uv run ./scripts/course_fetch.py`
- **预检本地选课列表合法性**：`uv run ./scripts/check_course.py`（需先执行前项脚本获取基础数据）

## 常见问题

- **首次执行 `uv run ./scripts/init.py` 后提示已创建 `config.yaml`**：这是正常行为。脚本会在配置文件不存在时按模板生成文件，此时请先补充 `cookie`，再重新运行一次初始化脚本。
- **`init.py` 无法获取 `name`、`profileId` 或 `semesterId`**：通常是 `cookie` 未填写完整或已失效。请重新登录选课系统后抓取最新请求头中的完整 `Cookie`。
- **启动后查询课程信息或查询选课状态失败**：优先检查 `domain`、`profileId`、`semesterId` 是否正确，以及当前网络是否可以正常访问选课系统。
- **开启 `skipPre` 后为什么不做余量检查**：这是设计行为。设为 `true` 后程序会跳过开跑前的余量探测，以减少一次查询开销，但也会失去基于当前余量的预过滤。
- **运行日志在哪里**：程序会在项目根目录自动创建 `logs/` 目录，并将每次运行的详细日志写入其中。

## 免责声明

本项目仅供技术研究与学习交流。因使用本工具选课或违反有关规定引发的风险与后果, 均自负。
