from api.schemas.asset.asset import ReadAssetRequest
from services import asset_service
from utils.log import logger


def map_uri_to_s3_url(uri: str | None) -> str:
    """
    Maps a URI to an S3 URL by retrieving the asset through the asset service.

    Args:
        uri (str | None): The URI to map to an S3 URL.

    Returns:
        str: The S3 URL of the asset, or an empty string if the URI is None
             or no asset is found.
    """
    if uri:
        try:
            s3_files = asset_service.read_assets(request=ReadAssetRequest(name=uri))
            if s3_files:
                return s3_files[0].url
        except Exception as e:
            logger.error(f"Error reading assets for URI {uri}: {e}")
    return ""
