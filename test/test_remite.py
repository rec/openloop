import os
from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast
from unittest.mock import Mock, patch


class Remite(Protocol):
    boto3: ModuleType

    def presigned_url(self, config: ModuleType, key: str) -> str: ...

    def main(self) -> None: ...


def load_remite() -> Remite:
    path = Path("auth/remite.ax.to/remite.py")
    spec = spec_from_file_location("remite", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Remite, module)


def test_presigned_url_uses_hetzner_s3v4_endpoint() -> None:
    remite = load_remite()
    config = ModuleType("config")
    config.__dict__.update(
        {
            "S3_ENDPOINT": "fsn1.your-objectstorage.com",
            "S3_REGION": "fsn1",
            "S3_BUCKET": "tapes",
            "ACCESS_KEY_ID": "access-key",
            "SECRET_ACCESS_KEY": "secret-key",
        }
    )
    client = Mock()
    client.generate_presigned_url.return_value = "https://download.example/tape.mp4"

    with patch.object(remite.boto3, "client", return_value=client) as create_client:
        url = remite.presigned_url(config, "totm/tape.mp4")

    assert url == "https://download.example/tape.mp4"
    create_client.assert_called_once_with(
        "s3",
        endpoint_url="https://fsn1.your-objectstorage.com",
        region_name="fsn1",
        aws_access_key_id="access-key",
        aws_secret_access_key="secret-key",
        config=create_client.call_args.kwargs["config"],
    )
    client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "tapes", "Key": "totm/tape.mp4"},
        ExpiresIn=300,
    )


def test_directory_index_lists_only_the_authenticated_group() -> None:
    remite = load_remite()
    config = ModuleType("config")
    config.__dict__.update(
        {
            "S3_ENDPOINT": "nbg1.your-objectstorage.com",
            "S3_REGION": "nbg1",
            "S3_BUCKET": "axto-private",
            "ACCESS_KEY_ID": "access-key",
            "SECRET_ACCESS_KEY": "secret-key",
            "PREFIXES": {"totm": "totm/", "oderg-in-duo": "oderg-in-duo/"},
        }
    )
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [{"Prefix": "totm/live/"}],
            "Contents": [
                {"Key": "totm/"},
                {"Key": "totm/notes & plans.pdf"},
            ],
        }
    ]
    output = StringIO()

    with (
        patch.object(remite, "load_config", return_value=config),
        patch.object(remite.boto3, "client", return_value=client),
        patch.dict(os.environ, {"REMOTE_USER": "totm", "REQUEST_URI": "/"}),
        redirect_stdout(output),
    ):
        remite.main()

    page = output.getvalue()
    assert "Status: 200 OK" in page
    assert "Content-Type: text/html; charset=utf-8" in page
    assert '<a href="/totm/live/">live/</a>' in page
    assert '<a href="/totm/notes%20%26%20plans.pdf">notes &amp; plans.pdf</a>' in page
    assert "oderg-in-duo" not in page
    client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="axto-private", Prefix="totm/", Delimiter="/"
    )


def test_other_group_directory_is_forbidden() -> None:
    remite = load_remite()
    config = ModuleType("config")
    config.__dict__["PREFIXES"] = {"totm": "totm/", "oderg-in-duo": "oderg-in-duo/"}
    output = StringIO()

    with (
        patch.object(remite, "load_config", return_value=config),
        patch.object(remite.boto3, "client") as create_client,
        patch.dict(
            os.environ,
            {"REMOTE_USER": "totm", "REQUEST_URI": "/oderg-in-duo/"},
        ),
        redirect_stdout(output),
    ):
        remite.main()

    assert "Status: 403 Forbidden" in output.getvalue()
    create_client.assert_not_called()


def test_nested_directory_links_back_to_parent() -> None:
    remite = load_remite()
    config = ModuleType("config")
    config.__dict__.update(
        {
            "S3_ENDPOINT": "nbg1.your-objectstorage.com",
            "S3_REGION": "nbg1",
            "S3_BUCKET": "axto-private",
            "ACCESS_KEY_ID": "access-key",
            "SECRET_ACCESS_KEY": "secret-key",
            "PREFIXES": {"totm": "totm/"},
        }
    )
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "totm/live/show.mp4"}]}
    ]
    output = StringIO()

    with (
        patch.object(remite, "load_config", return_value=config),
        patch.object(remite.boto3, "client", return_value=client),
        patch.dict(os.environ, {"REMOTE_USER": "totm", "REQUEST_URI": "/totm/live/"}),
        redirect_stdout(output),
    ):
        remite.main()

    page = output.getvalue()
    assert '<a href="/totm/">Parent directory</a>' in page
    assert '<a href="/totm/live/show.mp4">show.mp4</a>' in page
    client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="axto-private", Prefix="totm/live/", Delimiter="/"
    )
