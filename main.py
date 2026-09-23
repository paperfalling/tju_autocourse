"""Run course selection for the users in the local configuration."""

from tju_autocourse import run
from tju_autocourse.commands import cli

if __name__ == "__main__":
    raise SystemExit(cli(lambda: run("./config.yaml")))
