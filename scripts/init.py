"""Complete configuration fields using the configured authentication method."""

from tju_autocourse.commands import cli, initialize

if __name__ == "__main__":
    raise SystemExit(cli(initialize))
