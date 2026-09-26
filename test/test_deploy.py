from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import tyro

from scripts.deploy import Deploy


def test_dry_run_prints_commands_without_running_them() -> None:
    output = StringIO()
    deployment = Deploy(root=Path("/workspace"), dry_run=True)

    with redirect_stdout(output), patch("scripts.deploy.subprocess.run") as run:
        deployment.run()

    assert run.call_count == 0
    assert "ssh root@server.swirly.com" in output.getvalue()
    assert "rsync -av --chown=remite:remite" in output.getvalue()
    assert "/workspace/auth/remite_config.py" in output.getvalue()
    assert "--chown=ax:ax" in output.getvalue()


def test_short_dry_run_flag() -> None:
    assert tyro.cli(Deploy, args=["-d"]).dry_run
