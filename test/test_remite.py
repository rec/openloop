from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast
from unittest.mock import Mock, patch


class Remite(Protocol):
    boto3: ModuleType

    def presigned_url(self, config: ModuleType, key: str) -> str: ...


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
        url = remite.presigned_url(config, "group-a/tape.mp4")

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
        Params={"Bucket": "tapes", "Key": "group-a/tape.mp4"},
        ExpiresIn=300,
    )
