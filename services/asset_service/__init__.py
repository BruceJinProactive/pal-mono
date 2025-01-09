from api.schemas.asset.asset import AssetResponse, ReadAssetRequest, WriteAssetRequest

from . import _implementation


def write_asset(asset: WriteAssetRequest) -> AssetResponse:
    """Write assets to S3 bucket.

    Args:
        asset (WriteAssetRequest): The asset to write.

    Returns:
        AssetResponse: An asset object containing the S3 URL of the written file.
    """
    return _implementation.write_asset(asset)


def read_asset_by_name(request: ReadAssetRequest) -> AssetResponse:
    """Read single asset from s3 bucket via file name.

    Args:
        request (ReadAssetRequest): The asset object containing the name of the file to
            fetch.

    Returns:
        AssetResponse: An asset object containing the S3 URL of the fetched file.
    """
    return _implementation.read_asset_by_name(request)


def read_assets(request: ReadAssetRequest) -> list[AssetResponse]:
    """Read assets from S3 bucket.

    Args:
        request (ReadAssetRequest): The asset details to find by. Assets can fetched by
            matching name or metadata.

    Returns:
        list[AssetResponse]: A list of asset objects each containing the S3 URL of the
            fetched file.
    """
    return _implementation.read_assets(request)
