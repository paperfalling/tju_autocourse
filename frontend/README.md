# TJU AutoCourse WebUI

独立的 Vue 3 前端，不修改或依赖项目现有 Python 代码。

## 本地运行

```bash
cd frontend
npm install
npm run dev
```

默认连接项目的 `/api/v1` 后端。需要单独预览界面时，可以复制 `.env.example`
为 `.env.local`，将 `VITE_USE_MOCK` 改成 `true`。

真实请求封装位于 `src/api/client.ts`。开发环境会把 `/api` 转发到
`http://127.0.0.1:8000`。

完整开发联调需要同时启动后端：

```bash
# 项目根目录
uv run uvicorn web_api.main:app --reload --port 8000

# 另一个终端
cd frontend
npm run dev
```

生产式本机运行可先执行 `npm run build`，然后在项目根目录执行
`uv run ./scripts/web.py`，浏览器访问 `http://127.0.0.1:8000`。

## 构建

```bash
npm run build
```
