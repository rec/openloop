#!/home/remite/venv/bin/python
"""Authenticate a request through Apache and redirect it to Hetzner media."""

import os
import sys
from html import escape
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path, PurePosixPath
from types import ModuleType
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.client import BaseClient
from botocore.config import Config

CONFIG_PATH = Path("/home/remite/remite_config.py")


def presigned_url(config: ModuleType, key: str) -> str:
    """Return a five-minute URL for one Hetzner Object Storage download."""
    return s3_client(config).generate_presigned_url(
        "get_object",
        Params={"Bucket": config.S3_BUCKET, "Key": key},
        ExpiresIn=300,
    )


def s3_client(config: ModuleType) -> BaseClient:
    """Connect to the private Hetzner bucket."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.S3_ENDPOINT}",
        region_name=config.S3_REGION,
        aws_access_key_id=config.ACCESS_KEY_ID,
        aws_secret_access_key=config.SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def directory_index(config: ModuleType, key: str, group_prefix: str) -> str:
    """Render the current directory from objects in the authenticated group."""
    entries: list[tuple[str, str]] = []
    pages = (
        s3_client(config)
        .get_paginator("list_objects_v2")
        .paginate(Bucket=config.S3_BUCKET, Prefix=key, Delimiter="/")
    )
    for page in pages:
        for item in page.get("CommonPrefixes", []):
            child = item["Prefix"]
            entries.append((child[len(key) :], child))
        for item in page.get("Contents", []):
            child = item["Key"]
            if child != key:
                entries.append((child[len(key) :], child))

    lines = [
        "<!doctype html>",
        '<html lang="en">',
        '<meta charset="utf-8">',
        f"<title>{escape(key)}</title>",
        f"<h1>{escape(key)}</h1>",
    ]
    if key != group_prefix:
        parent = key.rstrip("/").rsplit("/", 1)[0] + "/"
        parent_url = "/" + quote(parent, safe="/")
        lines.append(f'<p><a href="{parent_url}">Parent directory</a></p>')
    lines.append("<ul>")
    for name, child in sorted(entries, key=lambda item: item[0].casefold()):
        lines.append(f'<li><a href="/{quote(child, safe="/")}">{escape(name)}</a></li>')
    lines.extend(["</ul>", "</html>"])
    return "\n".join(lines)


def load_config() -> ModuleType:
    """Load the server-only configuration file."""
    spec = spec_from_file_location("remite_config", CONFIG_PATH)
    if spec is None or spec.loader is None:
        sys.exit(f"Cannot load {CONFIG_PATH}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def requested_key() -> str | None:
    """Return the requested S3 key when its path is safe."""
    path = unquote(urlsplit(os.environ.get("REQUEST_URI", "")).path)
    key = path.lstrip("/")
    if any(part in {".", ".."} for part in PurePosixPath(key).parts):
        return None
    return key


def reply(status: str, body: str, content_type: str = "text/plain") -> None:
    """Return a CGI response."""
    print(f"Status: {status}")
    print(f"Content-Type: {content_type}; charset=utf-8")
    print("Cache-Control: no-store")
    print()
    print(body)


def main() -> None:
    """Authorize the Apache-authenticated user for one S3 prefix."""
    key = requested_key()
    if key is None:
        reply("404 Not Found", "Not found")
        return

    config = load_config()
    prefix = config.PREFIXES.get(os.environ.get("REMOTE_USER"))
    if prefix is None:
        reply("403 Forbidden", "Forbidden")
        return

    if not key:
        key = prefix
    if key == prefix.rstrip("/"):
        key = prefix
    if not key.startswith(prefix):
        reply("403 Forbidden", "Forbidden")
        return

    if key.endswith("/"):
        reply("200 OK", directory_index(config, key, prefix), "text/html")
        return

    target = presigned_url(config, key)
    print("Status: 302 Found")
    print(f"Location: {target}")
    print("Cache-Control: no-store")
    print()


if __name__ == "__main__":
    main()
