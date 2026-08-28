from __future__ import annotations

import copy
import datetime as dt
import os
import threading
from pathlib import Path
from typing import Any

import yaml

from tju_autocourse.config import validate_config


DEFAULT_META: dict[str, Any] = {
    "domain": "classes.tju.edu.cn",
    "profileId": 0,
    "semesterId": 0,
    "startTime": dt.datetime(1970, 1, 1, 8, 0, 0),
    "skipPre": False,
}


class ConfigStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {
                    "meta": copy.deepcopy(DEFAULT_META),
                    "users": [],
                }
            with self.path.open(encoding="utf-8") as file:
                loaded = yaml.safe_load(file) or {}
            meta = loaded.setdefault("meta", {}) or {}
            loaded["meta"] = meta
            for key, default in DEFAULT_META.items():
                if meta.get(key) is None:
                    meta[key] = copy.deepcopy(default)
            loaded.setdefault("users", [])
            return loaded

    def save(self, config: dict[str, Any]) -> None:
        config = copy.deepcopy(config)
        if config.get("users"):
            validate_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with self._lock:
            with temp_path.open("w", encoding="utf-8") as file:
                yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)
            os.replace(temp_path, self.path)

    def account_index(self, account_id: str) -> int:
        if not account_id.startswith("account-"):
            raise KeyError(account_id)
        try:
            index = int(account_id.removeprefix("account-"))
        except ValueError as exc:
            raise KeyError(account_id) from exc
        users = self.load().get("users", [])
        if index < 0 or index >= len(users):
            raise KeyError(account_id)
        return index

    def get_account(self, account_id: str) -> dict[str, Any]:
        config = self.load()
        return copy.deepcopy(config["users"][self.account_index(account_id)])

    def resolved_account(self, account_id: str) -> dict[str, Any]:
        config = self.load()
        user = copy.deepcopy(config["users"][self.account_index(account_id)])
        meta = config.get("meta", {})
        for key in ("domain", "profileId", "semesterId", "startTime", "skipPre"):
            if user.get(key) is None:
                user[key] = copy.deepcopy(meta.get(key, DEFAULT_META[key]))
            if user[key] is None:
                user[key] = copy.deepcopy(DEFAULT_META[key])
        return user

    @staticmethod
    def mask_cookie(cookie: str) -> str:
        if not cookie:
            return "未设置"
        first = cookie.split(";", 1)[0].strip()
        if "=" not in first:
            return "••••••••"
        name, value = first.split("=", 1)
        suffix = value[-4:] if len(value) >= 4 else "••••"
        return f"{name}=••••••••{suffix}"

    def public_account(self, index: int, user: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.load()
        user = copy.deepcopy(user if user is not None else config["users"][index])
        meta = config.get("meta", {})
        profile_id = user.get("profileId", meta.get("profileId", 0)) or 0
        semester_id = user.get("semesterId", meta.get("semesterId", 0)) or 0
        return {
            "id": f"account-{index}",
            "name": user.get("name") or f"用户 {index + 1}",
            "studentId": user.get("studentId", ""),
            "cookieMasked": self.mask_cookie(str(user.get("cookie", ""))),
            "profileId": profile_id,
            "semesterId": semester_id,
            "status": "valid" if user.get("cookie") and profile_id and semester_id else "checking",
        }
