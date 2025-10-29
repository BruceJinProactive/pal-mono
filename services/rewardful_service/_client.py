from typing import Any, Dict, List

import httpx

from utils.log import logger


class RewardfulClient:
    """Client for interacting with Rewardful REST API."""

    def __init__(
        self, api_secret: str, base_url: str = "https://api.getrewardful.com/v1"
    ):
        """
        Initialize Rewardful client.

        Args:
            api_secret: Rewardful API secret for authentication
            base_url: Base URL for Rewardful API (defaults to production)
        """
        self.api_secret = api_secret
        self.base_url = base_url
        self.auth = (api_secret, "")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] | None = None,
        data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to Rewardful API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data

        Returns:
            Dict[str, Any]: API response

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    auth=self.auth,
                    params=params,
                    json=data,
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Rewardful API error: {e.response.status_code} - {e.response.text}"
                )
                raise
            except Exception as e:
                logger.error(f"Rewardful API request failed: {e}")
                raise

    async def create_affiliate(
        self,
        email: str,
        first_name: str,
        last_name: str,
        campaign_id: str | None = None,
        token: str | None = None,
        stripe_customer_id: str | None = None,
        paypal_email: str | None = None,
        wise_email: str | None = None,
    ) -> Dict[str, Any]:
        """
        Create a new affiliate.

        Args:
            email: Affiliate's email address
            first_name: Affiliate's first name
            last_name: Affiliate's last name
            campaign_id: Campaign UUID (optional, uses default if not provided)
            token: Alphanumeric code for links (optional)
            stripe_customer_id: Stripe customer ID for customer referrals (optional)
            paypal_email: PayPal email for payouts (optional)
            wise_email: Wise email for payouts (optional)

        Returns:
            Dict[str, Any]: Created affiliate data
        """
        data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        }

        if campaign_id is not None:
            data["campaign_id"] = campaign_id
        if token is not None:
            data["token"] = token
        if stripe_customer_id is not None:
            data["stripe_customer_id"] = stripe_customer_id
        if paypal_email is not None:
            data["paypal_email"] = paypal_email
        if wise_email is not None:
            data["wise_email"] = wise_email

        return await self._request("POST", "affiliates", data=data)

    async def get_affiliate(
        self, affiliate_id: str, expand: List[str] | None = None
    ) -> Dict[str, Any]:
        """
        Retrieve an affiliate by ID.

        Args:
            affiliate_id: Rewardful affiliate ID
            expand: List of fields to expand (e.g., ["campaign", "links", "coupon"])

        Returns:
            Dict[str, Any]: Affiliate data
        """
        params: Dict[str, Any] = {}
        if expand:
            params["expand[]"] = expand

        return await self._request("GET", f"affiliates/{affiliate_id}", params=params)

    async def list_affiliates(
        self,
        limit: int = 100,
        page: int = 1,
        campaign_id: str | None = None,
        expand: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        List all affiliates.

        Args:
            limit: Number of results per page (max 100)
            page: Page number
            campaign_id: Filter by campaign ID
            expand: List of fields to expand

        Returns:
            Dict[str, Any]: Paginated affiliate list with metadata
        """
        params: Dict[str, Any] = {"limit": limit, "page": page}

        if campaign_id:
            params["campaign_id"] = campaign_id
        if expand:
            params["expand[]"] = expand

        return await self._request("GET", "affiliates", params=params)

    async def update_affiliate(
        self,
        affiliate_id: str,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        paypal_email: str | None = None,
        wise_email: str | None = None,
        state: str | None = None,
    ) -> Dict[str, Any]:
        """
        Update an affiliate.

        Args:
            affiliate_id: Rewardful affiliate ID
            email: New email address (optional)
            first_name: New first name (optional)
            last_name: New last name (optional)
            paypal_email: New PayPal email (optional)
            wise_email: New Wise email (optional)
            state: Affiliate state: "active" or "disabled" (optional)

        Returns:
            Dict[str, Any]: Updated affiliate data
        """
        data = {}
        if email is not None:
            data["email"] = email
        if first_name is not None:
            data["first_name"] = first_name
        if last_name is not None:
            data["last_name"] = last_name
        if paypal_email is not None:
            data["paypal_email"] = paypal_email
        if wise_email is not None:
            data["wise_email"] = wise_email
        if state is not None:
            data["state"] = state

        return await self._request("PUT", f"affiliates/{affiliate_id}", data=data)

    async def disable_affiliate(self, affiliate_id: str) -> Dict[str, Any]:
        """
        Disable an affiliate by setting state to "disabled".
        Rewardful doesn't support deletion, so we disable instead.

        Args:
            affiliate_id: Rewardful affiliate ID

        Returns:
            Dict[str, Any]: Updated affiliate data with state="disabled"
        """
        return await self.update_affiliate(affiliate_id=affiliate_id, state="disabled")
