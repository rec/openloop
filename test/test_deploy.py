from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import tomlkit
import tyro

from scripts.deploy import Deploy, render_config


def test_dry_run_prints_work_without_running_commands(tmp_path: Path) -> None:
    output = StringIO()
    apache = tmp_path / "auth/ax.to"
    apache.mkdir(parents=True)
    (apache / ".htaccess").write_text("")
    deployment = Deploy(root=tmp_path, dry_run=True)

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
    assert not (tmp_path / "secrets.toml").exists()


def test_first_deployment_saves_answers_and_reuses_them(tmp_path: Path) -> None:
    apache = tmp_path / "auth/ax.to"
    apache.mkdir(parents=True)
    (apache / ".htaccess").write_text("")
    deployment = Deploy(root=tmp_path)
    expected = {
        "groups": {"totm": "totm-value", "oderg-in-duo": "duo-value"},
        "cloudflare_account_id": "account-id",
        "cloudflare_token": "token-value",
    }
    with (
        patch(
            "builtins.input",
            side_effect=[
                "totm",
                "totm-value",
                "oderg-in-duo",
                "duo-value",
                "none",
                "account-id",
                "token-value",
                "y",
            ],
        ),
        patch("scripts.deploy.socket.gethostbyname", return_value="203.0.113.10"),
        patch("scripts.deploy.local_s3_credentials", return_value=("key", "secret")),
        patch.multiple(
            Deploy,
            configure_dns=Mock(),
            configure_bucket=Mock(),
            install_boto3=Mock(),
            upload_redirector=Mock(),
            write_config=Mock(),
            write_passwords=Mock(),
        ),
    ):
        deployment.run()

    path = tmp_path / "secrets.toml"
    assert tomlkit.parse(path.read_text()) == expected
    assert path.stat().st_mode & 0o777 == 0o600

    with (
        patch("builtins.input", side_effect=AssertionError("Unexpected prompt")),
        patch("scripts.deploy.socket.gethostbyname", return_value="203.0.113.10"),
        redirect_stdout(StringIO()) as output,
    ):
        Deploy(root=tmp_path, dry_run=True).run()

    assert "Groups: totm, oderg-in-duo" in output.getvalue()
    assert "Cloudflare account: account-id" in output.getvalue()
    assert "totm-value" not in output.getvalue()
    assert "duo-value" not in output.getvalue()
    assert "token-value" not in output.getvalue()


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
