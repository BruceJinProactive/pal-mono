from api.schemas.asset.asset import AssetResponse, ReadAssetRequest, WriteAssetRequest

from . import _implementation


def write_asset(
    file_name: str, content: bytes, metadata: dict[str, str] = {}
) -> AssetResponse:
    """Write assets to S3 bucket.

    Args:
        file_name (str): Name of the file to write.
        content (bytes): File content in bytes.
        metadata (dict[str, str], optional): Metadata to attach to the file. Defaults to {}.

    Returns:
        AssetResponse: S3 URL of the written file.
    """

    asset = WriteAssetRequest(name=file_name, content=content, metadata=metadata)
    return _implementation.write_asset(asset)


def read_asset(
    file_name: str | None = None, metadata: dict[str, str] = {}
) -> list[AssetResponse]:
    """Read assets from S3 bucket.

    Args:
        file_name (str | None, optional): Name of the file to read. Defaults to None.
        metadata (dict[str, str], optional): Metadata to filter by. Defaults to {}.

    Returns:
        list[AssetResponse]: A list of S3 URLs for the requested assets.
    """

    if not file_name and not metadata:
        raise ValueError("At least one of `file_name` or `metadata` must be provided.")

    asset = ReadAssetRequest(name=file_name, metadata=metadata)
    return _implementation.read_asset(asset)
