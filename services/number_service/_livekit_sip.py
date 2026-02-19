from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests
from livekit.api import AccessToken, SIPGrants, VideoGrants

from utils.log import logger


@dataclass
class LiveKitProvisionResult:
    """Result of provisioning a phone number for LiveKit."""

    trunk_id: str
    dispatch_rule_id: str


class LiveKitSIPClient:
    """Sync client for LiveKit SIP dispatch rule management.

    Uses AccessToken (sync JWT generation) + requests (sync HTTP)
    to call LiveKit's Twirp API endpoints.
    """

    def __init__(self):
        self._url = os.environ.get("LIVEKIT_URL", "")
        self._api_key = os.environ.get("LIVEKIT_API_KEY", "")
        self._api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
        self._inbound_trunk_id = os.environ.get("LIVEKIT_INBOUND_TRUNK_ID", "")

    def is_configured(self) -> bool:
        """Check if all LiveKit env vars are set."""
        return all(
            [
                self._url,
                self._api_key,
                self._api_secret,
                self._inbound_trunk_id,
            ]
        )

    def _generate_token(self) -> str:
        """Generate a LiveKit JWT with SIP admin grants."""
        token = AccessToken(
            api_key=self._api_key,
            api_secret=self._api_secret,
        )
        token.with_grants(VideoGrants(room_create=True, room_admin=True))
        token.with_sip_grants(SIPGrants(admin=True, call=True))
        return token.to_jwt()

    def _twirp_url(self, method: str) -> str:
        """Build a Twirp API URL."""
        base = self._url.rstrip("/")
        return f"{base}/twirp/livekit.SIP/{method}"

    def _headers(self) -> dict[str, str]:
        jwt = self._generate_token()
        return {
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        }

    def create_dispatch_rule(
        self, phone_number: str, metadata: Optional[str] = None
    ) -> LiveKitProvisionResult:
        """Create a SIP dispatch rule for a phone number.

        Maps incoming calls on the shared trunk for this phone number
        to a LiveKit room handled by the agent worker.

        Args:
            phone_number: E.164 phone number (e.g., '+15551234567')
            metadata: Optional metadata to attach to the dispatch rule

        Returns:
            LiveKitProvisionResult with trunk_id and dispatch_rule_id

        Raises:
            ValueError: If the API call fails
        """
        # Strip the + prefix for matching — LiveKit SIP uses raw digits
        clean_number = phone_number.lstrip("+")

        payload: dict = {
            "trunk_ids": [self._inbound_trunk_id],
            "rule": {
                "dispatchRuleIndividual": {
                    "roomPrefix": f"call-{clean_number}-",
                }
            },
            "name": f"inbound-{clean_number}",
        }
        if metadata:
            payload["metadata"] = metadata

        try:
            response = requests.post(
                self._twirp_url("CreateSIPDispatchRule"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            if response.status_code != 200:
                raise ValueError(
                    f"LiveKit CreateSIPDispatchRule failed: "
                    f"HTTP {response.status_code} - {response.text}"
                )

            data = response.json()
            dispatch_rule_id = data.get("sipDispatchRuleId", "")
            if not dispatch_rule_id:
                raise ValueError(
                    "LiveKit CreateSIPDispatchRule returned empty dispatch rule ID"
                )

            logger.info(
                "Created LiveKit SIP dispatch rule",
                extra={
                    "phone_number": phone_number,
                    "dispatch_rule_id": dispatch_rule_id,
                    "trunk_id": self._inbound_trunk_id,
                },
            )

            return LiveKitProvisionResult(
                trunk_id=self._inbound_trunk_id,
                dispatch_rule_id=dispatch_rule_id,
            )

        except requests.RequestException as e:
            raise ValueError(f"LiveKit API request failed: {e}") from e

    def find_dispatch_rule_by_number(self, phone_number: str) -> Optional[str]:
        """Find a SIP dispatch rule ID by phone number.

        Queries LiveKit's ListSIPDispatchRule API and matches by the
        rule name convention `inbound-{digits}`.

        Args:
            phone_number: E.164 phone number (e.g., '+15551234567')

        Returns:
            The dispatch rule ID if found, None otherwise

        Raises:
            ValueError: If the API call fails
        """
        clean_number = phone_number.lstrip("+")
        expected_name = f"inbound-{clean_number}"

        try:
            response = requests.post(
                self._twirp_url("ListSIPDispatchRule"),
                json={},
                headers=self._headers(),
                timeout=15,
            )
            if response.status_code != 200:
                raise ValueError(
                    f"LiveKit ListSIPDispatchRule failed: "
                    f"HTTP {response.status_code} - {response.text}"
                )

            data = response.json()
            for rule in data.get("items", []):
                if rule.get("name") == expected_name:
                    return rule.get("sipDispatchRuleId", "")

            return None

        except requests.RequestException as e:
            raise ValueError(f"LiveKit API request failed: {e}") from e

    def has_dispatch_rule(self, phone_number: str) -> bool:
        """Check if a phone number has a LiveKit dispatch rule.

        Args:
            phone_number: E.164 phone number

        Returns:
            True if a dispatch rule exists for this number
        """
        try:
            return self.find_dispatch_rule_by_number(phone_number) is not None
        except ValueError:
            return False

    def delete_dispatch_rule(self, dispatch_rule_id: str) -> None:
        """Delete a SIP dispatch rule by ID.

        Args:
            dispatch_rule_id: The dispatch rule ID to delete

        Raises:
            ValueError: If the API call fails
        """
        payload = {
            "sipDispatchRuleId": dispatch_rule_id,
        }

        try:
            response = requests.post(
                self._twirp_url("DeleteSIPDispatchRule"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            if response.status_code != 200:
                raise ValueError(
                    f"LiveKit DeleteSIPDispatchRule failed: "
                    f"HTTP {response.status_code} - {response.text}"
                )

            logger.info(
                "Deleted LiveKit SIP dispatch rule",
                extra={"dispatch_rule_id": dispatch_rule_id},
            )

        except requests.RequestException as e:
            raise ValueError(f"LiveKit API request failed: {e}") from e

    def delete_dispatch_rule_by_number(self, phone_number: str) -> None:
        """Find and delete the SIP dispatch rule for a phone number.

        Args:
            phone_number: E.164 phone number

        Raises:
            ValueError: If the API call fails or no rule found
        """
        rule_id = self.find_dispatch_rule_by_number(phone_number)
        if not rule_id:
            logger.warning(
                "No LiveKit dispatch rule found for phone number",
                extra={"phone_number": phone_number},
            )
            return
        self.delete_dispatch_rule(rule_id)
