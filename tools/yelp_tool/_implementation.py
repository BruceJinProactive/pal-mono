import traceback
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.yelp_tool._apis import get_openings, get_yelp_bearer_token
from tools.yelp_tool._utils import create_openings_request, format_openings_for_llm
from tools.yelp_tool.classes import YelpAccessToken, YelpAccessTokenRequest
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class YelpTool(Toolkit):
    def __init__(
        self,
        business_id_or_alias: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="yelp_tool")

        self.business_id_or_alias = business_id_or_alias
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata

        self.register(self.get_restaurant_openings)

    @cached_property
    def _yelp_bearer_token(self) -> YelpAccessToken:
        client_id = get_client_secret_with_fallback("YELP_CLIENT_ID")
        client_secret = get_client_secret_with_fallback("YELP_CLIENT_SECRET")

        bearer_token = get_yelp_bearer_token(
            request_params=YelpAccessTokenRequest(
                client_id=client_id,
                client_secret=client_secret,
                code="PLACEHOLDER",
                grant_type="PLACEHOLDER",
            )
        )

        if not bearer_token:
            raise Exception("Failed to obtain Yelp access token")

        return YelpAccessToken(**bearer_token.model_dump())

    @tool
    def get_restaurant_openings(
        self,
        covers: int,
        date: str,
        time: str,
        get_covers_range: bool = False,
    ) -> str:
        """
        Get available reservation times for a restaurant using the Yelp Bookings API.

        This function returns available reservation times around the requested timeslot
        and across several days (typically 4 days: day before, current day, and 2 days after).
        Currently, only openings with "credit_card_required": false are returned.

        Args:
            covers (int): Number of people for the reservation (1-10)
            date (str): Date for the reservation in YYYY-MM-DD format (e.g., '2024-12-25')
            time (str): Time for the reservation in HH:MM format (e.g., '18:30')
            get_covers_range (bool): Whether to include covers range information in response

        Returns:
            str: Formatted string containing available reservation times, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            success, message, request_obj = create_openings_request(
                business_id_or_alias=self.business_id_or_alias,
                covers=covers,
                date=date,
                time=time,
                get_covers_range=get_covers_range,
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            response = get_openings(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            formatted_response = format_openings_for_llm(response)
            return formatted_response

        except Exception as e:
            logger.debug(
                f"[YelpTool.get_restaurant_openings] Error getting openings: {e}"
            )
            logger.debug(traceback.format_exc())
            return "Failed to get restaurant openings. Please try again."
