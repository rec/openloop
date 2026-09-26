"""Provision and deploy the password-protected media redirector."""

import json
import re
import socket
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from shlex import join, quote
from typing import Annotated
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import boto3
import tyro
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel

CLOUDFLARE_ACCOUNT_ID = "44066e01f0c0660a57222615b9fc72e1"
GROUP_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")


class Deploy(BaseModel, frozen=True):
    """Provision remite.ax.to and deploy its Hetzner redirector."""

    root: Path = Path(__file__).resolve().parents[1]
    remote: str = "root@server.swirly.com"
    dry_run: Annotated[bool, tyro.conf.arg(aliases=["-d"])] = False
    """Print the intended work without changing anything."""

    def run(self) -> None:
        """Request configuration, confirm it, then provision the redirector."""
        groups = prompt_groups()
        bucket = prompt_value("Hetzner bucket: ")
        region = prompt_value("Hetzner region [fsn1]: ", "fsn1")
        endpoint = prompt_value(
            f"Hetzner endpoint [{region}.your-objectstorage.com]: ",
            f"{region}.your-objectstorage.com",
        )
        cloudflare_account_id = prompt_value(
            f"Cloudflare account ID [{CLOUDFLARE_ACCOUNT_ID}]: ",
            CLOUDFLARE_ACCOUNT_ID,
        )
        cloudflare_token = prompt_value("Cloudflare API token: ")
        access_key_id = prompt_value("Hetzner S3 access key: ")
        secret_access_key = prompt_value("Hetzner S3 secret key: ")
        virtualmin_password = prompt_value("Virtualmin login value for remite: ")
        server_ip = socket.gethostbyname("server.swirly.com")
        self.print_summary(
            groups,
            bucket,
            region,
            endpoint,
            cloudflare_account_id,
            server_ip,
        )
        if input("Proceed? [y/N] ").lower() != "y":
            return
        if self.dry_run:
            self.print_dry_run(groups, bucket, region, endpoint, server_ip)
            return

        self.configure_dns(cloudflare_account_id, cloudflare_token, server_ip)
        self.configure_bucket(
            bucket,
            region,
            endpoint,
            access_key_id,
            secret_access_key,
        )
        self.configure_virtualmin(virtualmin_password)
        self.install_boto3()
        self.upload_redirector()
        self.write_config(
            groups,
            bucket,
            region,
            endpoint,
            access_key_id,
            secret_access_key,
        )
        self.write_passwords(groups)
        print("Update /home/ax/public_html/.htaccess with:\n")
        print((self.root / "auth/ax.to/.htaccess").read_text())

    def configure_dns(self, account_id: str, token: str, server_ip: str) -> None:
        """Create or update the direct Cloudflare record for remite.ax.to."""
        zones = cloudflare_request(
            token,
            "GET",
            "/zones?" + urlencode({"account.id": account_id, "name": "ax.to"}),
        )
        if not zones:
            sys.exit("Cloudflare could not find the ax.to zone")
        zone_id = zones[0]["id"]
        records = cloudflare_request(
            token,
            "GET",
            f"/zones/{zone_id}/dns_records?"
            + urlencode({"type": "A", "name": "remite.ax.to"}),
        )
        record = {
            "type": "A",
            "name": "remite.ax.to",
            "content": server_ip,
            "ttl": 300,
            "proxied": False,
        }
        if records:
            cloudflare_request(
                token,
                "PUT",
                f"/zones/{zone_id}/dns_records/{records[0]['id']}",
                record,
            )
        else:
            cloudflare_request(token, "POST", f"/zones/{zone_id}/dns_records", record)

    def configure_bucket(
        self,
        bucket: str,
        region: str,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        """Create the bucket when needed and remove public access policies."""
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{endpoint}",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
                raise
            client.create_bucket(
                Bucket=bucket,
                ACL="private",
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        try:
            client.delete_bucket_policy(Bucket=bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchBucketPolicy"}:
                raise
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                client.put_object_acl(Bucket=bucket, Key=item["Key"], ACL="private")

    def configure_virtualmin(self, password: str) -> None:
        """Create the Virtualmin host and request its certificate."""
        command = (
            "set -eu\n"
            "if ! virtualmin list-domains --name-only | "
            "grep -Fx remite.ax.to >/dev/null; then\n"
            "  virtualmin create-domain \\\n"
            "    --domain remite.ax.to \\\n"
            "    --desc 'Object Storage media redirector' \\\n"
            "    --user remite \\\n"
            "    --passfile /dev/stdin \\\n"
            "    --unix --dir --web --ssl --logrotate --limits-from-plan\n"
            "fi\n"
            "virtualmin generate-letsencrypt-cert --domain remite.ax.to --web\n"
        )
        self.run_command(["ssh", self.remote, command], password + "\n")

    def install_boto3(self) -> None:
        """Create the remite virtual environment and install its dependency."""
        command = (
            "set -eu\n"
            "if ! apachectl -M 2>/dev/null | grep -qE 'cgi(d)?_module'; then\n"
            "  a2enmod cgid || a2enmod cgi\n"
            "  systemctl reload apache2\n"
            "fi\n"
            "if [ ! -x /home/remite/venv/bin/python ]; then\n"
            "  runuser -u remite -- python3 -m venv /home/remite/venv\n"
            "fi\n"
            "runuser -u remite -- /home/remite/venv/bin/pip install boto3\n"
        )
        self.run_command(["ssh", self.remote, command])

    def upload_redirector(self) -> None:
        """Upload the CGI program and its Apache configuration."""
        auth = self.root / "auth"
        self.run_command(
            [
                "rsync",
                "-av",
                "--chown=remite:remite",
                "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
                str(auth / "remite.ax.to/.htaccess"),
                f"{self.remote}:/home/remite/public_html/",
            ]
        )
        self.run_command(
            [
                "rsync",
                "-av",
                "--chown=remite:remite",
                "--chmod=Du=rwx,Dgo=rx,Fu=rwx,Fgo=rx",
                str(auth / "remite.ax.to/remite.py"),
                f"{self.remote}:/home/remite/public_html/",
            ]
        )

    def write_config(
        self,
        groups: dict[str, str],
        bucket: str,
        region: str,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        """Write the server-only boto3 configuration through SSH."""
        command = (
            "set -eu\n"
            "umask 077\n"
            "cat > /home/remite/remite_config.py\n"
            "chown remite:remite /home/remite/remite_config.py\n"
            "chmod 600 /home/remite/remite_config.py\n"
        )
        self.run_command(
            ["ssh", self.remote, command],
            render_config(
                groups, bucket, region, endpoint, access_key_id, secret_access_key
            ),
        )

    def write_passwords(self, groups: dict[str, str]) -> None:
        """Replace the Apache password file with the requested shared accounts."""
        for index, (name, password) in enumerate(groups.items()):
            create = " -c" if index == 0 else ""
            command = (
                f"htpasswd{create} -i /home/remite/.htpasswd {quote(name)}\n"
                "chown remite:remite /home/remite/.htpasswd\n"
                "chmod 640 /home/remite/.htpasswd\n"
            )
            self.run_command(["ssh", self.remote, command], password + "\n")

    def run_command(self, command: list[str], input: str | None = None) -> None:
        """Run one command, or print it in dry-run mode."""
        if self.dry_run:
            print(join(command))
            return
        subprocess.run(command, input=input, text=True, check=True)

    def print_summary(
        self,
        groups: dict[str, str],
        bucket: str,
        region: str,
        endpoint: str,
        cloudflare_account_id: str,
        server_ip: str,
    ) -> None:
        """Print the non-secret deployment configuration for confirmation."""
        print("Groups: " + ", ".join(groups))
        print(f"Hetzner bucket: {bucket}")
        print(f"Hetzner endpoint: {endpoint} ({region})")
        print(f"Cloudflare account: {cloudflare_account_id}")
        print(f"Server: {self.remote}")
        print(f"remite.ax.to: {server_ip}")
        print("The bucket policy and every existing object ACL will become private.")
        print("You must make this top-level .htaccess change yourself:\n")
        print((self.root / "auth/ax.to/.htaccess").read_text())

    def print_dry_run(
        self,
        groups: dict[str, str],
        bucket: str,
        region: str,
        endpoint: str,
        server_ip: str,
    ) -> None:
        """Describe the operations that would run after confirmation."""
        print(f"Cloudflare: set remite.ax.to to {server_ip}")
        print(f"Hetzner: create {bucket} in {region} at {endpoint} if needed")
        print(f"Hetzner: make {bucket} and its objects private")
        print("Virtualmin: create remite.ax.to if needed and request its certificate")
        print("Server: enable Apache CGI support if needed, then install boto3")
        print("Server: upload the CGI and Apache configuration")
        print("Server: write the server-only Hetzner configuration")
        print("Server: replace Apache accounts for " + ", ".join(groups))


def cloudflare_request(
    token: str,
    method: str,
    path: str,
    body: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Make one authenticated Cloudflare API request."""
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"https://api.cloudflare.com/client/v4{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request) as response:
            payload = json.load(response)
    except HTTPError as error:
        sys.exit(f"Cloudflare API error: {error.read().decode()}")
    if not isinstance(payload, dict) or payload.get("success") is not True:
        sys.exit(f"Cloudflare API error: {payload}")
    result = payload.get("result")
    if not isinstance(result, list):
        sys.exit(f"Cloudflare API returned an unexpected result: {payload}")

    records: list[dict[str, object]] = []
    for item in result:
        if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
            sys.exit(f"Cloudflare API returned an unexpected result: {payload}")
        records.append(item)
    return records


def prompt_groups() -> dict[str, str]:
    """Prompt for each shared account and its password."""
    groups: dict[str, str] = {}
    while name := input("Group name (blank or none when done): ").strip():
        if name == "none":
            break
        if GROUP_NAME.fullmatch(name) is None:
            print("Group names use lowercase letters, numbers, and hyphens.")
            continue
        if name in groups:
            print("That group already exists.")
            continue
        groups[name] = prompt_value(f"Access value for {name}: ")
    if not groups:
        sys.exit("At least one group is required")
    return groups


def prompt_value(prompt: str, default: str = "") -> str:
    """Prompt until a value is provided, or use the supplied default."""
    while not (value := input(prompt).strip() or default):
        print("A value is required.")
    return value


def render_config(
    groups: dict[str, str],
    bucket: str,
    region: str,
    endpoint: str,
    access_key_id: str,
    secret_access_key: str,
) -> str:
    """Render the server-only configuration from the interactive answers."""
    prefixes = {name: f"{name}/" for name in groups}
    return "\n".join(
        [
            f"S3_ENDPOINT = {endpoint!r}",
            f"S3_REGION = {region!r}",
            f"S3_BUCKET = {bucket!r}",
            f"ACCESS_KEY_ID = {access_key_id!r}",
            f"SECRET_ACCESS_KEY = {secret_access_key!r}",
            f"PREFIXES = {prefixes!r}",
            "",
        ]
    )


if __name__ == "__main__":
    tyro.cli(Deploy).run()
