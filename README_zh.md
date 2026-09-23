# TJU AutoCourse

[English](README.md)

天津大学 EAMS 自动选课工具，支持浏览器 Cookie 和 SSO 学号密码登录。使用 Python 3.13+、`requests` 和每用户独立线程；每个用户只有一个活动会话，请求串行执行。

## 安装与运行

```powershell
uv sync
Copy-Item config.template.yaml config.yaml
# 编辑 config.yaml 中的认证和课程目标
uv run scripts/init.py
uv run scripts/course_fetch.py
uv run scripts/check_course.py
uv run main.py
```

初始化工具补全缺失的用户名、学期和选课轮次，多个轮次时交互选择；只保存成功获取的字段，失败不会把用户配置替换为空。配置文件不存在时，首次初始化只复制模板，不访问学校服务。课程拉取保存完整课程和余量快照，即使 `skipPre=true` 也会查询余量。课程检查只读取本地快照。

主程序先获取课程与已选课程，启用余量预检查时还获取余量；必需查询失败会停止该用户。准备完成后等待 `startTime`，再开始提交选课请求。无时区时间按运行机器本地时区解释，不自动转换为 UTC。使用 Ctrl+C 可以中止等待或持续重试，正在执行的 HTTP 请求会在返回或超时后关闭。

## 配置与认证

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
      cookie: "完整 Cookie"
    profileId: 4420
    semesterId: 134
    targets:
      - group_name: 体育
        limit: 1
        courses: ["06488", "06491"]
```

轮次与学期示例值需按自己的实际配置修改，或删除后运行初始化工具。每个用户可以覆盖 `meta` 中的业务配置，显式 `skipPre: false` 同样有效。认证必须放在用户自己的 `auth` 中。

SSO 用户把整个 `auth` 替换为：

```yaml
auth:
  type: sso
  username: "学号"
  password: "密码"
  retries: 2
```

Cookie 导入目标 EAMS 域名的 Cookie jar，并接受服务器更新；明确失效后停止该用户。SSO 首次登录最多尝试 `1 + retries` 次；每次业务请求检测到掉线，最多重登 `retries` 次。重登创建新会话，验证登录并恢复选课轮次后重试原操作；仅登录成功不会重置恢复预算。`retries: 0` 禁用这些重试。认证失败只影响对应用户。

SSO 使用 TJU CAS 流程：向 `learning.twt.edu.cn/enc` 发送学号、密码与登录令牌的拼接值，向同站点 `/ocr` 发送验证码图片。这是外部辅助服务依赖；CAS/EAMS 与辅助服务使用独立会话。验证码识别、协议变化或辅助服务故障可能导致登录失败。

课程序号必须使用带引号的字符串。配置写回时始终保留引号和前导零，避免 YAML 1.1/1.2 解析差异把 `02058` 读成数字 `2058`。如果文件中的值已经变为数字，程序会提示按实际课程序号修正，不会自动猜测补零。`course_fetch.py` 不写入配置文件。

## 调度与策略

严格按组顺序和组内 `courses` 顺序执行。当前组达到限额或候选耗尽才进入下一组，不回头轮询已结束的组。`limit=-1` 不限、`0` 跳过、正数限制**本轮明确成功数**。已有课程用于冲突检查，不计入本轮成功数。

时间冲突及课程代码重复始终直接过滤；课程号不存在也跳过。启用余量预检查时，快照已满或缺少该课程余量会直接跳过，先于响应策略执行。

`skipPre=true` 仅绕过余量检查。开放后余量可能不能实时更新，需要绕过过期快照时由用户显式开启；程序不按钟点自动切换。例如设置 12 点开始并开启 `skipPre`，可以避免过期快照在请求前淘汰目标。要对快照已满的课程使用 `full: retry`，也需要开启 `skipPre`。

| 响应 | 默认动作 | 含义 |
| --- | --- | --- |
| `not_open` | `retry` | 不开放，持续重试当前候选 |
| `too_fast` | `retry` | 点击过快，按间隔重试当前候选 |
| `full` | `skip` | 已满，切换候选 |
| `already_selected` | `skip` | 已选过，切换候选，不增加成功数 |
| `unknown` | `skip` | 超时、网关错误或未知正文，记录后切换候选 |

成功固定更新计数和已选课程；掉线固定交给认证模块。这两类不允许配置业务策略。按本系统的使用假设，“不开放”是同一轮次的全局状态，因此默认不换课探测；解析器目前不能进一步区分“尚未开始”和“已经结束”。持续重试也可能持续等待已经结束的轮次，需要用户中止或设置有限重试。

支持 `retry`、`skip`、`stop` 三个动作，`stop` 停止整个用户本轮选课。有限重试例子：

```yaml
selection_policy:
  full:
    action: retry
    max_retries: 3
    on_exhausted: skip
```

`max_retries` 表示首次尝试之外允许安排的额外重试，省略表示无限，`0` 表示不重试。有限预算的 `on_exhausted` 默认为 `skip`，也可为 `stop`。不适用的字段、负预算和未知动作在启动时拒绝。

策略支持 `meta → 用户 → 目标组` 三层覆盖，**每种响应整条替换**，未提及的响应继承上层。因此组内 `full: retry` 明确表示无限重试，不继承全局的次数限制。每个候选按响应分别累计预算，响应交替和 SSO 重登不重置，下一候选重新计数。

同一用户所有实际 EAMS 请求的发送起点至少相隔 **0.55 秒**，包括组合查询、失败重试和新会话请求。不同用户独立计时；SSO 和辅助服务不使用 EAMS 的间隔，但仍有请求超时。该间隔是客户端保证，不保证服务器不会再返回“过快”。

默认对选课结果未知时**不查询确认**，将请求机会给下一候选。服务器可能已选上超时的请求，因此实际选中数可能超过客户端计数或组限额。这是吞吐量优先的既定策略，用户需在结束后自行检查实际课表。

## 代码结构与验证

模块职责、请求调用链、状态归属与修改入口见 [架构说明](docs/architecture.md)。

配置模块解析继承，认证与会话模块维护身份及生命周期，EAMS 模块提供类型化请求，纯调度模块维护进度和策略预算，应用模块负责时间与多用户运行。日志仅由入口初始化，解析失败不会伪装成空课表。日志位于 `logs/`；快照保持 `data/course_info_<name>.json` 和 `data/course_statu_<name>.json` 格式。

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
```

测试使用模拟 HTTP、真实 Requests Cookie jar、虚拟时钟和临时文件，不连接真实学校服务。两种认证的真实验收还需用有效凭证完成登录、轮次初始化与课程查询；执行 `scripts/course_fetch.py` 可做只读联调，它不会提交选课请求。离线测试通过不代表真实 SSO 已验证。

请勿提交密码、Cookie、本地配置或原始响应。项目仅用于技术研究与学习，使用者自行遵守学校规定。
