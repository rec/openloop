"""Deploy the password-protected Hetzner Object Storage redirector."""

import subprocess
from pathlib import Path
from shlex import join
from typing import Annotated

import tyro
from pydantic import BaseModel


class Deploy(BaseModel, frozen=True):
    """Install and deploy the remite.ax.to CGI redirector."""

    root: Path = Path(__file__).resolve().parents[1]
    remote: str = "root@server.swirly.com"
    dry_run: Annotated[bool, tyro.conf.arg(aliases=["-d"])] = False
    """Print deployment commands without running them."""

    def run(self) -> None:
        """Install boto3 remotely, then upload the required deployment files."""
        auth = self.root / "auth"
        commands = [
            [
                "ssh",
                self.remote,
                "set -eu\n"
                "if [ ! -x /home/remite/venv/bin/python ]; then\n"
                "  runuser -u remite -- python3 -m venv /home/remite/venv\n"
                "fi\n"
                "runuser -u remite -- /home/remite/venv/bin/pip install boto3\n",
            ],
        ]
        file_modes = "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r,Fx=rx"
        commands.append(
            [
                "rsync",
                "-av",
                "--chown=remite:remite",
                file_modes,
                str(auth / "remite.ax.to/.htaccess"),
                str(auth / "remite.ax.to/remite.py"),
                f"{self.remote}:/home/remite/public_html/",
            ]
        )
        commands.append(
            [
                "rsync",
                "-av",
                "--chown=remite:remite",
                "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=",
                str(auth / "remite_config.py"),
                f"{self.remote}:/home/remite/remite_config.py",
            ]
        )
        commands.append(
            [
                "rsync",
                "-av",
                "--chown=ax:ax",
                file_modes,
                str(auth / "ax.to/.htaccess"),
                f"{self.remote}:/home/ax/public_html/.htaccess",
            ]
        )
        if self.dry_run:
            for command in commands:
                print(join(command))
            return
        for command in commands:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    tyro.cli(Deploy).run()
