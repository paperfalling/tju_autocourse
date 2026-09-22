# -*- coding: utf-8 -*-
# @Time    : 2025/09/05 20:07
# @Author  : papersus
# @File    : main.py
import tju_autocourse as atc
from tju_autocourse.commands import cli

if __name__ == "__main__":
    raise SystemExit(cli(lambda: atc.run("./config.yaml")))
