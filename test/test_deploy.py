from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import tyro

from scripts.deploy import Deploy, render_config


def test_dry_run_prints_work_without_running_commands() -> None:
    output = StringIO()
    deployment = Deploy(root=Path.cwd(), dry_run=True)

    with (
        redirect_stdout(output),
        patch(
            "builtins.input",
            side_effect=[
                "group-a",
                "group-a-password",
                "group-b",
                "group-b-password",
                "",
                "",
                "cf",
                "vm",
                "y",
            ],
        ),
        patch("scripts.deploy.socket.gethostbyname", return_value="203.0.113.10"),
        patch("scripts.deploy.subprocess.run") as run,
    ):
        deployment.run()

    assert run.call_count == 0
    assert "Groups: group-a, group-b" in output.getvalue()
    assert "Cloudflare: set remite.ax.to to 203.0.113.10" in output.getvalue()
    assert "Hetzner: make axto-private and its objects private" in output.getvalue()


def test_render_config_keeps_passwords_out() -> None:
    config = render_config(
        {"group-a": "group-a-password", "group-b": "group-b-password"},
        "axto-private",
        "fsn1",
        "fsn1.your-objectstorage.com",
        "access-key",
        "secret-key",
    )

    assert "group-a-password" not in config
    assert "group-b-password" not in config
    assert "PREFIXES = {'group-a': 'group-a/', 'group-b': 'group-b/'}" in config


def test_short_dry_run_flag() -> None:
    assert tyro.cli(Deploy, args=["-d"]).dry_run
