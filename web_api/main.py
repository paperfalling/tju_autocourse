from __future__ import annotations

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from tju_autocourse.user import init_logger

from .config_store import ConfigStore
from .schemas import AccountCreate, AccountUpdate, SettingsUpdate, TargetsUpdate, TaskCreate
from .services import fetch_courses, initialize_account
from .task_manager import TaskManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def failure(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message, "data": None})


def create_app(config_path: str | Path | None = None, serve_frontend: bool = True) -> FastAPI:
    store = ConfigStore(config_path or PROJECT_ROOT / "config.yaml")
    manager = TaskManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_logger()
        sink_id = logger.add(manager.loguru_sink, format="{message}")
        try:
            yield
        finally:
            logger.remove(sink_id)
            for task in manager.tasks.values():
                if task.worker and not task.worker.done():
                    task.worker.cancel()

    app = FastAPI(
        title="TJU AutoCourse Web API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.config_store = store
    app.state.task_manager = manager
    app.state.course_cache = {}
    app.state.service_lock = asyncio.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        message = exc.errors()[0].get("msg", "请求参数不正确") if exc.errors() else "请求参数不正确"
        return failure("VALIDATION_ERROR", str(message), 422)

    @app.exception_handler(KeyError)
    async def missing_resource(_: Request, exc: KeyError) -> JSONResponse:
        return failure("NOT_FOUND", f"资源不存在：{exc.args[0]}", 404)

    @app.exception_handler(ValueError)
    async def invalid_operation(_: Request, exc: ValueError) -> JSONResponse:
        return failure("INVALID_OPERATION", str(exc), 400)

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Web API 未处理异常：{type(exc).__name__}")
        return failure("INTERNAL_ERROR", "服务内部错误，请查看后端日志", 500)

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return success({"status": "ok"})

    @app.get("/api/v1/settings")
    async def get_settings() -> dict[str, Any]:
        return success(store.load().get("meta", {}))

    @app.put("/api/v1/settings")
    async def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
        config = store.load()
        for key, value in payload.model_dump(exclude_none=True).items():
            config.setdefault("meta", {})[key] = value
        store.save(config)
        return success(config["meta"], "设置已保存")

    @app.get("/api/v1/accounts")
    async def list_accounts() -> dict[str, Any]:
        users = store.load().get("users", [])
        return success([store.public_account(index, user) for index, user in enumerate(users)])

    @app.post("/api/v1/accounts", status_code=201)
    async def create_account(payload: AccountCreate) -> Any:
        config = store.load()
        user = payload.model_dump(exclude={"should_validate"}, exclude_none=True)
        user.setdefault("targets", [])
        if payload.should_validate:
            try:
                user = await initialize_account(user)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                return failure("COOKIE_INVALID", str(exc) or "账号验证失败", 400)
        config.setdefault("users", []).append(user)
        store.save(config)
        index = len(config["users"]) - 1
        return success(store.public_account(index, user), "账号已添加")

    @app.patch("/api/v1/accounts/{account_id}")
    async def update_account(account_id: str, payload: AccountUpdate) -> dict[str, Any]:
        config = store.load()
        index = store.account_index(account_id)
        config["users"][index].update(payload.model_dump(exclude_none=True))
        store.save(config)
        app.state.course_cache.pop(account_id, None)
        return success(store.public_account(index, config["users"][index]), "账号已更新")

    @app.delete("/api/v1/accounts/{account_id}")
    async def delete_account(account_id: str) -> dict[str, Any]:
        config = store.load()
        index = store.account_index(account_id)
        config["users"].pop(index)
        store.save(config)
        app.state.course_cache.clear()
        return success(None, "账号已删除")

    @app.post("/api/v1/accounts/{account_id}/initialize")
    async def initialize_existing_account(account_id: str) -> Any:
        config = store.load()
        index = store.account_index(account_id)
        try:
            initialized = await initialize_account(store.resolved_account(account_id))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            return failure("COOKIE_INVALID", str(exc) or "账号验证失败", 400)
        preserved_targets = config["users"][index].get("targets", [])
        initialized["targets"] = preserved_targets
        config["users"][index] = initialized
        store.save(config)
        return success(store.public_account(index, initialized), "账号信息已更新")

    @app.get("/api/v1/accounts/{account_id}/courses")
    async def list_courses(account_id: str, keyword: str = "", refresh: bool = False) -> dict[str, Any]:
        cache = app.state.course_cache.get(account_id)
        if cache is None or refresh:
            config = store.load()
            account = store.resolved_account(account_id)
            if not account.get("profileId") or not account.get("semesterId"):
                raise ValueError("请先验证账号并获取学期与选课轮次")
            async with app.state.service_lock:
                cache = await fetch_courses(account, config.get("meta", {}))
            app.state.course_cache[account_id] = cache
        query = keyword.strip().lower()
        result = cache
        if query:
            result = [
                course for course in cache
                if any(query in str(course.get(field, "")).lower() for field in ("name", "no", "code", "teacher"))
            ]
        return success(result)

    @app.get("/api/v1/accounts/{account_id}/targets")
    async def get_targets(account_id: str) -> dict[str, Any]:
        account = store.get_account(account_id)
        groups = [
            {
                "id": f"group-{index}",
                "name": target.get("group_name", f"课程组 {index + 1}"),
                "limit": target.get("limit", 1),
                "courseNos": target.get("courses", []),
            }
            for index, target in enumerate(account.get("targets", []))
        ]
        return success(groups)

    @app.put("/api/v1/accounts/{account_id}/targets")
    async def update_targets(account_id: str, payload: TargetsUpdate) -> dict[str, Any]:
        config = store.load()
        index = store.account_index(account_id)
        config["users"][index]["targets"] = [
            {"group_name": group.name, "limit": group.limit, "courses": group.courseNos}
            for group in payload.groups
        ]
        store.save(config)
        return await get_targets(account_id)

    @app.post("/api/v1/accounts/{account_id}/validate")
    async def validate_targets(account_id: str) -> dict[str, Any]:
        account = store.get_account(account_id)
        configured = [number for target in account.get("targets", []) for number in target.get("courses", [])]
        course_response = await list_courses(account_id)
        available_numbers = {course["no"] for course in course_response["data"]}
        missing = [number for number in configured if number not in available_numbers]
        return success({"valid": not missing, "missingCourseNos": missing})

    @app.get("/api/v1/tasks")
    async def list_tasks() -> dict[str, Any]:
        return success(manager.list())

    @app.post("/api/v1/tasks", status_code=201)
    async def create_task(payload: TaskCreate) -> dict[str, Any]:
        config = store.load()
        account_configs = [store.resolved_account(account_id) for account_id in payload.accountIds]
        task = manager.create(
            copy.deepcopy(account_configs),
            copy.deepcopy(config.get("meta", {})),
            payload.startTime,
            payload.skipPrecheck,
        )
        return success(task.public(), "任务已创建")

    @app.get("/api/v1/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        task = manager.get(task_id)
        return success({**task.public(), "logs": list(task.logs)})

    @app.post("/api/v1/tasks/{task_id}/stop")
    async def stop_task(task_id: str) -> dict[str, Any]:
        task = manager.get(task_id)
        if task.status in {"completed", "failed", "stopped"}:
            raise ValueError("任务已经结束")
        manager.stop(task_id)
        return success(task.public(), "停止请求已发送")

    @app.get("/api/v1/tasks/{task_id}/events")
    async def task_events(task_id: str) -> StreamingResponse:
        manager.get(task_id)

        async def stream():
            async for event in manager.subscribe(task_id):
                if event is None:
                    yield ": heartbeat\n\n"
                    continue
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event['event']}\ndata: {data}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if serve_frontend and frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
