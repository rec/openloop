#!/home/remite/venv/bin/python
"""Authenticate a request through Apache and redirect it to Hetzner media."""

import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path, PurePosixPath
from types import ModuleType
from urllib.parse import unquote, urlsplit

import boto3
from botocore.config import Config

CONFIG_PATH = Path("/home/remite/remite_config.py")


def presigned_url(config: ModuleType, key: str) -> str:
    """Return a five-minute URL for one Hetzner Object Storage download."""
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{config.S3_ENDPOINT}",
        region_name=config.S3_REGION,
        aws_access_key_id=config.ACCESS_KEY_ID,
        aws_secret_access_key=config.SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": config.S3_BUCKET, "Key": key},
        ExpiresIn=300,
    )


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
    if not key or any(part in {".", ".."} for part in PurePosixPath(key).parts):
        return None
    return key


def reply(status: str, body: str) -> None:
    """Return a plain CGI response."""
    print(f"Status: {status}")
    print("Content-Type: text/plain; charset=utf-8")
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
    if prefix is None or not key.startswith(prefix):
        reply("403 Forbidden", "Forbidden")
        return

    target = presigned_url(config, key)
    print("Status: 302 Found")
    print(f"Location: {target}")
    print("Cache-Control: no-store")
    print()


if __name__ == "__main__":
    main()
