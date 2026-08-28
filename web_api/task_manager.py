from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from loguru import logger

from tju_autocourse.config import set_config_meta

from .services import create_web_users


@dataclass
class ManagedTask:
    id: str
    account_names: list[str]
    start_time: dt.datetime
    target_count: int
    status: str = "scheduled"
    progress: int = 0
    success_count: int = 0
    error: str | None = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now().astimezone())
    worker: asyncio.Task[None] | None = field(default=None, repr=False)
    logs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500), repr=False)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "accountName": "、".join(self.account_names),
            "status": self.status,
            "startTime": self.start_time.isoformat(),
            "progress": self.progress,
            "successCount": self.success_count,
            "targetCount": self.target_count,
            "error": self.error,
            "createdAt": self.created_at.isoformat(),
        }


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, ManagedTask] = {}
        self._execution_lock = asyncio.Lock()
        self._log_sequence = 0

    def create(
        self,
        account_configs: list[dict[str, Any]],
        meta: dict[str, Any],
        start_time: dt.datetime,
        skip_precheck: bool,
    ) -> ManagedTask:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        task_id = f"task_{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}"
        target_count = sum(
            max(0, int(target.get("limit", 0)))
            for account in account_configs
            for target in account.get("targets", [])
        )
        task = ManagedTask(
            id=task_id,
            account_names=[str(account.get("name", "未命名账号")) for account in account_configs],
            start_time=start_time,
            target_count=target_count,
        )
        self.tasks[task_id] = task
        task.worker = asyncio.create_task(
            self._run(task, account_configs, dict(meta), skip_precheck),
            name=task_id,
        )
        self.publish_status(task)
        return task

    async def _run(
        self,
        task: ManagedTask,
        account_configs: list[dict[str, Any]],
        meta: dict[str, Any],
        skip_precheck: bool,
    ) -> None:
        watcher: asyncio.Task[None] | None = None
        try:
            async with self._execution_lock:
                meta["startTime"] = task.start_time
                meta["skipPre"] = skip_precheck
                for account in account_configs:
                    account["startTime"] = task.start_time
                    account["skipPre"] = skip_precheck
                set_config_meta(meta)
                with logger.contextualize(task_id=task.id):
                    users = create_web_users(account_configs)
                    watcher = asyncio.create_task(self._mark_running_at_start(task))
                    logger.info(f"任务 {task.id} 已创建，等待执行")
                    await asyncio.gather(*(user.start() for user in users))
                    task.success_count = sum(len(user.done) for user in users)
                    task.progress = 100
                    task.status = "completed"
                    logger.success(f"任务 {task.id} 已完成，成功选中 {task.success_count} 门课程")
                    self.publish_status(task)
        except asyncio.CancelledError:
            task.status = "stopped"
            task.error = None
            self.publish_log(task.id, "WARNING", "任务已由用户停止")
            self.publish_status(task)
        except Exception as exc:  # noqa: BLE001 - task errors must be reported to the UI
            task.status = "failed"
            task.error = str(exc)
            self.publish_log(task.id, "ERROR", f"任务执行失败：{exc}")
            self.publish_status(task)
        finally:
            if watcher is not None:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

    async def _mark_running_at_start(self, task: ManagedTask) -> None:
        now = dt.datetime.now().astimezone()
        start_time = task.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=now.tzinfo)
        await asyncio.sleep(max(0.0, (start_time - now).total_seconds()))
        if task.status == "scheduled":
            task.status = "running"
            self.publish_status(task)

    def stop(self, task_id: str) -> ManagedTask:
        task = self.get(task_id)
        if task.worker and not task.worker.done():
            task.worker.cancel()
        return task

    def get(self, task_id: str) -> ManagedTask:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise KeyError(task_id) from exc

    def list(self) -> list[dict[str, Any]]:
        return [task.public() for task in reversed(self.tasks.values())]

    def publish_status(self, task: ManagedTask) -> None:
        self._publish(task, {"event": "task.status", "data": task.public()})

    def publish_log(self, task_id: str, level: str, message: str) -> None:
        task = self.tasks.get(task_id)
        if task is None:
            return
        self._log_sequence += 1
        log = {
            "id": self._log_sequence,
            "time": dt.datetime.now().astimezone().strftime("%H:%M:%S"),
            "level": level if level in {"INFO", "SUCCESS", "WARNING", "ERROR"} else "INFO",
            "message": message,
        }
        task.logs.append(log)
        self._publish(task, {"event": "task.log", "data": log})

    def loguru_sink(self, message: Any) -> None:
        record = message.record
        task_id = record["extra"].get("task_id")
        if task_id:
            self.publish_log(str(task_id), record["level"].name, record["message"])

    def _publish(self, task: ManagedTask, event: dict[str, Any]) -> None:
        for queue in tuple(task.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    async def subscribe(self, task_id: str) -> AsyncIterator[dict[str, Any] | None]:
        task = self.get(task_id)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        task.subscribers.add(queue)
        try:
            yield {"event": "task.status", "data": task.public()}
            for log in task.logs:
                yield {"event": "task.log", "data": log}
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield None
        finally:
            task.subscribers.discard(queue)
