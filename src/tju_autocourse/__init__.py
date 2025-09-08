# -*- coding: utf-8 -*-
# @Time    : 2025/09/02 18:14
# @Author  : papersus
# @File    : __init__.py
from .api import run, create_user, create_users, set_config_meta
import os


__all__ = ["run", "create_user", "create_users", "set_config_meta"]


if not os.path.exists("./logs"):
    os.mkdir("./logs")
