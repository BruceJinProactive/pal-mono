import base64
import json
import re
import urllib.error
from datetime import datetime, timedelta, timezone
from functools import cached_property
from typing import Any, Dict, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.resy_tool_with_reservation._apikey import get_resy_api_key
from tools.resy_tool_with_reservation._client import (
    ResyAPIError,
    authorize_venue,
    cancel_reservation,
    create_guest,
    create_reservation,
    create_reservation_lock,
    extract_reservation_rows,
    fetch_reservations_report,
    find_resy_availability,
    get_reservation_refund_token,
    login_resy_account,
    refresh_universal_token,
    search_guest_by_phone,
)
from tools.resy_tool_with_reservation._utils import (
    extract_resy_availability,
    format_resy_availability,
    normalize_reservation_datetime,
)
from utils.log import logger


class ResyToolWithReservation(Toolkit, BaseReservationTool):
    """
    Reservation assistant that surfaces Resy availability and can complete bookings.

    The tool expects a Resy universal auth token in its configuration. It refreshes that
    token and scopes it to the venue on each booking attempt before calling the Control API.
    """

    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = [
        "party_size",
        "date",
        "time",
        "first_name",
        "last_name",
        "phone_number",
    ]
    REQUIRED_DELETE_RESERVATION_FIELDS = ["date"]

    def __init__(
        self,
        venue_id: int | str,
        city: str,
        venue_name: str,
        username: str,
        password: str,
        default_struct_tags: Optional[Sequence[Dict[str, Any]]] = None,
        tool_metadata: ToolMetadata | None = None,
    ):
        super().__init__(name="resy_tool_with_reservation")

        try:
            parsed_venue_id = int(venue_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Resy venue_id is required") from exc

        if not parsed_venue_id:
            raise ValueError("Resy venue_id is required")

        city = (city or "").strip()
        if not city:
            raise ValueError("Resy city is required")

        venue_name = (venue_name or "").strip()
        if not venue_name:
            raise ValueError("Resy venue name is required")

        username = (username or "").strip()
        password = (password or "").strip()
        if not username or not password:
            raise ValueError("Resy username and password are required")

        self.venue_id = parsed_venue_id
        self.city = city
        self.venue_name = venue_name
        self.username = username
        self.password = password
        self.base_auth_token: Optional[str] = None
        self._cached_operational_token: Optional[str] = None
        self._operational_token_expiry: Optional[datetime] = None
        self._analytics_token: Optional[str] = None
        self.tool_metadata = tool_metadata
        self.default_struct_tags = (
            list(default_struct_tags) if default_struct_tags else None
        )

        self.register(self.check_availability)
        self.register(self.make_reservation)
        self.register(self.delete_reservation)

    @cached_property
    def booking_base_url(self) -> str:
        """Return the deep-link base for booking."""

        return f"https://resy.com/cities/{self.city}/venues/{self.venue_name}"

    def _search_resy(self, *, day: str, party_size: int) -> dict:
        return find_resy_availability(
            venue_id=self.venue_id,
            city=self.city,
            venue_name=self.venue_name,
            day=day,
            party_size=party_size,
        )

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check reservation availability for the Resy venue.

        Args:
            party_size: Number of guests for the reservation.
            date: Desired reservation date in YYYY-MM-DD format.
            time: Desired reservation time in HH:MM (24-hour) format.

        Returns:
            The exact requested time if available, otherwise up to 5 closest alternatives.
        """

        party_size = (
            2 if party_size == 1 else party_size
        )  # 2 people minimum for checking

        try:
            with LLMObs.task(name="search_resy_availability"):
                response = self._search_resy(day=date, party_size=party_size)
        except urllib.error.HTTPError as exc:
            body = (
                exc.read().decode("utf-8", errors="ignore")
                if hasattr(exc, "read")
                else ""
            )
            logger.error(
                "[Resy Tool] HTTP error during availability search",
                extra={"code": exc.code, "reason": exc.reason, "body": body},
            )
            return (
                f"Error searching availability for venue {self.venue_id}: "
                f"HTTP {exc.code} {exc.reason}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error during availability search",
                exc_info=True,
            )
            return f"Error searching availability for venue {self.venue_id}: {exc}"

        slots = extract_resy_availability(response, party_size=party_size)
        if not slots:
            logger.debug(
                "[Resy Tool] No availability",
                extra={"venue_id": self.venue_id, "party_size": party_size},
            )
            return f"No availability found for venue {self.venue_id} (Party of {party_size})."

        try:
            requested_dt = datetime.fromisoformat(f"{date}T{time}")
        except ValueError:
            requested_dt = None

        formatted = format_resy_availability(
            slots, party_size=party_size, requested_time=requested_dt
        )
        logger.debug("[Resy Tool] Formatted availability: %s", formatted)
        return formatted

    @tool
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        date: str,
        time: str,
        first_name: str,
        last_name: str,
        phone_number: str,
        email: str = "",
        notes: str = "",
    ) -> str:
        """
        Books and completes the requested reservation on Resy. Do not make up the first name, last name and phone number, make sure to get that info from the user if you dont have it. Only use this function if the user explicitly tells you to make the reservation.
        Always call `check_availability` beforehand to ensure the slot is still open. Only use the function once, do not call it multiple times for the same reservation.

        Args:
            name: Optional guest name (ignored by this tool).
            party_size: Number of guests for the reservation.
            date: Desired reservation date in YYYY-MM-DD format.
            time: Desired reservation time in HH:MM (24-hour) format.
            first_name: Guest first name for the reservation.
            last_name: Guest last name for the reservation.
            phone_number: Guest phone number in E.164 format
            email: Optional guest email address. (ignored by this tool)
            notes: Optional notes supplied by the agent (ignored by this tool).

        Returns:
            A confirmation string describing the reservation status, or an error message.
        """

        try:
            normalized_dt = normalize_reservation_datetime(date, time)
        except ValueError as exc:
            logger.error(
                "[Resy Tool] Invalid reservation datetime",
                extra={"date": date, "time": time, "error": str(exc)},
            )
            return f"Error: Invalid reservation time: {exc}"

        target_dt = datetime.fromisoformat(normalized_dt)
        availability_response: Dict[str, Any]
        try:
            with LLMObs.task(name="search_resy_availability"):
                availability_response = self._search_resy(
                    day=date, party_size=party_size
                )
        except urllib.error.HTTPError as exc:
            body = (
                exc.read().decode("utf-8", errors="ignore")
                if hasattr(exc, "read")
                else ""
            )
            logger.error(
                "[Resy Tool] HTTP error while fetching availability before booking",
                extra={"code": exc.code, "reason": exc.reason, "body": body},
            )
            return (
                f"Error searching availability for venue {self.venue_id}: "
                f"HTTP {exc.code} {exc.reason}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while fetching availability",
                exc_info=True,
            )
            return f"Error searching availability for venue {self.venue_id}: {exc}"

        slots = extract_resy_availability(availability_response, party_size=party_size)
        if not slots:
            logger.debug(
                "[Resy Tool] No availability before booking attempt",
                extra={"venue_id": self.venue_id, "party_size": party_size},
            )
            return "Unable to find an available slot at that time on Resy. "

        matching_slot = self._find_slot_for_datetime(slots, target_dt)
        if not matching_slot:
            logger.debug(
                "[Resy Tool] Exact slot missing from availability results",
                extra={
                    "venue_id": self.venue_id,
                    "party_size": party_size,
                    "target": normalized_dt,
                },
            )
            return "The requested time is no longer available on Resy. "

        slot_token = matching_slot.get("token")
        template_id = matching_slot.get("template_id")
        service_type_id = matching_slot.get("service_type_id")
        config_type = (matching_slot.get("area") or "").strip() or "Dining Room"

        if not slot_token or not template_id or not service_type_id:
            logger.error(
                "[Resy Tool] Missing booking metadata in slot",
                extra={
                    "slot_token": bool(slot_token),
                    "template_id": template_id,
                    "service_type_id": service_type_id,
                },
            )
            return "I couldn't gather the required slot details from Resy. "

        try:
            api_key = get_resy_api_key(city=self.city, venue_name=self.venue_name)
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Failed to retrieve API key for booking", exc_info=True
            )
            return "Unable to retrieve Resy credentials at the moment. "

        try:
            operational_token = self._get_operational_token(api_key=api_key)
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error during authentication",
                extra={"status": exc.status, "reason": exc.reason},
            )
            self._invalidate_operational_token()
            return "Resy authentication failed while preparing the booking. "
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error during authentication", exc_info=True
            )
            self._invalidate_operational_token()
            return "Unable to authenticate with Resy right now. "

        try:
            guest_user_id = self._find_or_create_guest(
                api_key=api_key,
                auth_token=operational_token,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
            )
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error during guest lookup/creation",
                extra={"status": exc.status, "reason": exc.reason},
            )
            if exc.status in {401, 403}:
                self._invalidate_operational_token()
            return "Resy rejected the guest information (phone number or name). "
        except RuntimeError as exc:
            logger.error("[Resy Tool] Guest lookup/creation failed", exc_info=True)
            return str(exc)
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while handling guest", exc_info=True
            )
            return "Unable to process the guest information on Resy right now. Please try again later."

        if not guest_user_id:
            logger.error("[Resy Tool] Guest response missing id")
            return "Resy returned an unexpected guest response. "

        try:
            guest_user_id_int = int(guest_user_id)
        except (TypeError, ValueError):
            guest_user_id_int = guest_user_id

        api_time = target_dt.strftime("%H:%M:%S")

        lock_response: Dict[str, Any]
        try:
            with LLMObs.task(name="resy_create_lock"):
                lock_response = create_reservation_lock(
                    api_key=api_key,
                    auth_token=operational_token,
                    venue_id=self.venue_id,
                    date=date,
                    time=api_time,
                    party_size=party_size,
                    template_id=template_id,
                    config_type=config_type,
                    service_type_id=service_type_id,
                )
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error while creating lock",
                extra={"status": exc.status, "reason": exc.reason},
            )
            if exc.status in {401, 403}:
                self._invalidate_operational_token()
            return "Resy could not lock that time slot. It may have just been booked. "
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while creating lock", exc_info=True
            )
            return "Unable to secure the time slot on Resy right now."

        lock_token = lock_response.get("lock_token") or (
            (lock_response.get("lock") or {}).get("token")
        )
        if not lock_token:
            logger.error(
                "[Resy Tool] Lock response missing token",
                extra={"response": lock_response},
            )
            return "Failed to secure the Resy slot. Please try again or share the manual booking link."

        reservation_response: Dict[str, Any]
        try:
            with LLMObs.task(name="resy_confirm_reservation"):
                reservation_response = create_reservation(
                    api_key=api_key,
                    auth_token=operational_token,
                    venue_id=self.venue_id,
                    template_id=template_id,
                    config_type=config_type,
                    slot_token=slot_token,
                    lock_token=lock_token,
                    guest_user_id=guest_user_id_int,
                    party_size=party_size,
                    date=date,
                    time=api_time,
                    service_type_id=service_type_id,
                    first_name=first_name,
                    last_name=last_name,
                    phone_number=phone_number,
                    struct_tags=self.default_struct_tags,
                )
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error while confirming reservation",
                extra={"status": exc.status, "reason": exc.reason},
            )
            if exc.status in {401, 403}:
                self._invalidate_operational_token()
            return "Resy did not accept the reservation request. "
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while confirming reservation",
                exc_info=True,
            )
            return "Unable to finalize the reservation on Resy."

        reservation_id = reservation_response.get(
            "reservation_id"
        ) or reservation_response.get("id")
        confirmed_dt = (
            self._extract_reservation_datetime(reservation_response) or target_dt
        )
        pretty_datetime = confirmed_dt.strftime("%A, %B %d, %Y at %I:%M %p")
        slot_timezone = (matching_slot.get("timezone") or "").strip()
        if slot_timezone:
            pretty_datetime = f"{pretty_datetime} ({slot_timezone})"

        guest_display = name.strip() if name and name.strip() else None
        if not guest_display:
            guest_display = f"{first_name} {last_name}".strip()

        summary_lines = [
            "Reservation successfully created with Resy.",
            f"Reservation ID: {reservation_id}" if reservation_id else None,
            (
                f"Guest: {guest_display} (party of {party_size})"
                if guest_display
                else None
            ),
            f"Date & Time: {pretty_datetime}",
        ]
        summary_lines.append(
            "Let the guest know that they will receive a confirmation text from Resy the day before their reservation."
        )

        logger.debug(
            "[Resy Tool] Reservation created",
            extra={
                "venue_id": self.venue_id,
                "reservation_id": reservation_id,
                "guest_id": guest_user_id_int,
            },
        )

        return "\n".join(line for line in summary_lines if line)

    @tool
    @params_validate()
    def delete_reservation(self, date: str) -> str:  # type: ignore[misc]
        """Cancel the first reservation on a given date that matches the caller's phone. Make sure to ask for the specific date of the reservation they want to cancel if they didn't provide it. This tool doesnt support editing reservations, only cancelling.
        Args:
            date: Desired reservation date in YYYY-MM-DD format."""

        customer_phone = (
            self.tool_metadata.customer_phone if self.tool_metadata else None
        )
        if not customer_phone:
            return "I don't have the caller's phone number, so I can't identify the reservation to cancel."

        normalized_customer = _normalize_phone(customer_phone)
        if not normalized_customer:
            return "The caller's phone number appears to be invalid."

        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            return "Please provide the reservation date in YYYY-MM-DD format."

        try:
            api_key = get_resy_api_key(city=self.city, venue_name=self.venue_name)
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Failed to discover API key for cancellation",
                exc_info=True,
            )
            return "I couldn't load the Resy API key needed to manage reservations."

        try:
            operational_token = self._get_operational_token(api_key=api_key)
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Failed to acquire operational token",
                exc_info=True,
            )
            return "I couldn't authenticate with Resy to manage reservations."

        day_of_year = target_date.timetuple().tm_yday

        analytics_token = self._analytics_token
        if not analytics_token:
            # force refresh to fetch analytics token
            try:
                operational_token = self._get_operational_token(
                    api_key=api_key, force_refresh=True
                )
                analytics_token = self._analytics_token
            except Exception:  # noqa: BLE001
                logger.error(
                    "[Resy Tool] Failed to refresh tokens for analytics access",
                    exc_info=True,
                )
                return (
                    "I couldn't refresh the credentials needed to look up reservations."
                )

        if not analytics_token:
            logger.error(
                "[Resy Tool] Missing analytics token after venue authorization",
                extra={"venue_id": self.venue_id},
            )
            return "I couldn't locate the credentials needed to search the reservation list."

        try:
            report = fetch_reservations_report(
                api_key=api_key,
                services_auth_token=analytics_token,
                year=target_date.year,
                day_of_year=day_of_year,
            )
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Failed to fetch reservations report",
                extra={"date": date},
                exc_info=True,
            )
            return "I wasn't able to retrieve the reservation list from Resy."

        rows = extract_reservation_rows(report)
        customer_last_digits = normalized_customer[-10:]
        matching_row: Optional[Dict[str, Any]] = None
        for row in rows:
            row_phone = _normalize_phone(row.get("phone"))
            if not row_phone:
                continue
            if row_phone == normalized_customer or row_phone.endswith(
                customer_last_digits
            ):
                matching_row = row
                break

        if not matching_row:
            return "I didn't find any reservations for that date under the caller's phone number. Please verify that it's the correct date for the reservation to be cancelled."

        reservation_id_raw = matching_row.get("Reservation_id")
        reservation_id = str(reservation_id_raw).strip() if reservation_id_raw else ""
        if not reservation_id:
            logger.warning(
                "[Resy Tool] Matching reservation row missing Reservation_id",
                extra={"row": matching_row},
            )
            return "I found a reservation that matches the caller, but it is missing an identifier."

        try:
            refund_response = get_reservation_refund_token(
                api_key=api_key,
                auth_token=operational_token,
                reservation_id=reservation_id,
            )
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error while fetching refund token",
                extra={"status": exc.status, "reason": exc.reason},
            )
            if exc.status in {401, 403}:
                self._invalidate_operational_token()
            return "Resy did not authorize the cancellation request."
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while fetching refund token",
                exc_info=True,
            )
            return "I ran into an issue while preparing to cancel the reservation."

        refund_token = (refund_response or {}).get("token")
        if not refund_token:
            logger.error(
                "[Resy Tool] Refund token missing in response",
                extra={"reservation_id": reservation_id, "response": refund_response},
            )
            return "Resy didn't return the token required to cancel the reservation."

        try:
            cancel_response = cancel_reservation(
                api_key=api_key,
                auth_token=operational_token,
                reservation_id=reservation_id,
                refund_token=refund_token,
            )
        except ResyAPIError as exc:
            logger.error(
                "[Resy Tool] Resy API error while cancelling reservation",
                extra={"status": exc.status, "reason": exc.reason},
            )
            if exc.status in {401, 403}:
                self._invalidate_operational_token()
            return "Resy did not accept the cancellation request."
        except Exception:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while cancelling reservation",
                exc_info=True,
            )
            return "I hit an unexpected error while cancelling the reservation."

        guest_name = matching_row.get("Guest") or "the guest"
        time_value = matching_row.get("Time") or "unknown time"

        logger.info(
            "[Resy Tool] Reservation cancelled",
            extra={
                "reservation_id": reservation_id,
                "guest_name": guest_name,
                "date": date,
                "time": time_value,
            },
        )

        status = (
            cancel_response.get("status") if isinstance(cancel_response, dict) else None
        )
        confirmation = f"Cancelled the reservation for {guest_name} on {date} at {time_value}. Let the guest know the date and time of the cancelled reservation."
        if isinstance(status, dict):
            status_hint = status.get("status_id") or status.get("id")
            if status_hint:
                confirmation += f" (Resy status code: {status_hint})."

        return confirmation

    def _find_slot_for_datetime(
        self, slots: list[Dict[str, Any]], target: datetime
    ) -> Optional[Dict[str, Any]]:
        for slot in slots:
            slot_dt = self._parse_slot_start(slot.get("start"))
            if not slot_dt:
                continue

            slot_timezone = (slot.get("timezone") or "").strip()
            comparable = slot_dt

            if slot_timezone:
                try:
                    tz = ZoneInfo(slot_timezone)
                    if slot_dt.tzinfo:
                        comparable = slot_dt.astimezone(tz)
                    else:
                        comparable = slot_dt.replace(tzinfo=tz)
                except ZoneInfoNotFoundError:
                    comparable = slot_dt
            elif slot_dt.tzinfo:
                comparable = slot_dt.astimezone()

            if comparable.tzinfo:
                comparable = comparable.astimezone().replace(
                    second=0, microsecond=0, tzinfo=None
                )
            else:
                comparable = comparable.replace(second=0, microsecond=0)

            if comparable == target:
                return slot
        return None

    @staticmethod
    def _parse_slot_start(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _extract_reservation_datetime(
        reservation: Dict[str, Any],
    ) -> Optional[datetime]:
        specs = reservation.get("specs") or {}
        booked = specs.get("booked_datetime")
        if not booked:
            return None
        normalized = booked.replace(" ", "T")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _get_operational_token(
        self, *, api_key: str, force_refresh: bool = False
    ) -> str:
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and self._cached_operational_token
            and self._operational_token_expiry
            and self._operational_token_expiry - now > timedelta(minutes=1)
            and self._analytics_token
        ):
            return self._cached_operational_token

        base_token = self._ensure_base_token(
            api_key=api_key, force_refresh=force_refresh
        )

        try:
            refresh_response = refresh_universal_token(
                api_key=api_key, universal_token=base_token
            )
        except ResyAPIError as exc:
            if exc.status in {401, 403}:
                base_token = self._ensure_base_token(
                    api_key=api_key, force_refresh=True
                )
                refresh_response = refresh_universal_token(
                    api_key=api_key, universal_token=base_token
                )
            else:
                raise
        refresh_token = refresh_response.get("token")
        if not refresh_token:
            raise RuntimeError("Resy auth refresh did not return a token")

        self.base_auth_token = refresh_token

        venue_response = authorize_venue(
            api_key=api_key, universal_token=refresh_token, venue_id=self.venue_id
        )
        operational_token = venue_response.get("token")
        if not operational_token:
            raise RuntimeError("Resy venue authentication did not return a token")

        os_tokens = venue_response.get("os_tokens") or {}
        analytics_token = os_tokens.get("analytics")
        if analytics_token:
            self._analytics_token = analytics_token
        else:
            logger.warning(
                "[Resy Tool] Venue auth response missing analytics token",
                extra={"venue_id": self.venue_id},
            )

        expiry = self._extract_token_expiry(operational_token)
        if not expiry:
            expiry = now + timedelta(minutes=5)
        self._cached_operational_token = operational_token
        self._operational_token_expiry = expiry
        return operational_token

    def _invalidate_operational_token(self) -> None:
        self._cached_operational_token = None
        self._operational_token_expiry = None
        self._analytics_token = None
        self.base_auth_token = None

    def _ensure_base_token(self, *, api_key: str, force_refresh: bool = False) -> str:
        if self.base_auth_token and not force_refresh:
            return self.base_auth_token

        auth_response = login_resy_account(
            api_key=api_key,
            email=self.username,
            password=self.password,
            legacy=True,
        )
        token = auth_response.get("token")
        if not token:
            raise RuntimeError("Resy authentication did not return a token")

        self.base_auth_token = token
        return token

    @staticmethod
    def _extract_token_expiry(token: str) -> Optional[datetime]:
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload_segment = parts[1]
            padded = payload_segment + "=" * (-len(payload_segment) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
            payload = json.loads(decoded.decode("utf-8"))
            exp = payload.get("exp")
            if exp is None:
                return None
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
        except Exception:  # noqa: BLE001
            return None

    def _find_or_create_guest(
        self,
        *,
        api_key: str,
        auth_token: str,
        first_name: str,
        last_name: str,
        phone_number: str,
    ) -> Optional[int | str]:
        formatted_query = _format_phone_for_resy(phone_number)
        search_candidates = [formatted_query]

        users: Sequence[Dict[str, Any]] = []
        for candidate in search_candidates:
            try:
                search_response = search_guest_by_phone(
                    api_key=api_key,
                    auth_token=auth_token,
                    phone_number=candidate,
                )
            except ResyAPIError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[Resy Tool] Unexpected error searching guestbook", exc_info=True
                )
                raise RuntimeError(
                    "Unable to search existing guests on Resy right now. Please try again later."
                ) from exc

            users = search_response.get("users") or []
            if users:
                break

        if users:
            normalized_target = _normalize_phone(formatted_query)
            for candidate in users:
                candidate_number = _normalize_phone(candidate.get("mobile_number"))
                if candidate_number and candidate_number == normalized_target:
                    return candidate.get("id") or candidate.get("user_id")
            # No exact match; treat as not found so we attempt creation below.

        try:
            guest_response = create_guest(
                api_key=api_key,
                auth_token=auth_token,
                first_name=first_name,
                last_name=last_name,
                phone_number=formatted_query,
            )
        except ResyAPIError:
            # Propagate to caller
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error while creating guest", exc_info=True
            )
            raise RuntimeError(
                "Unable to register the guest on Resy right now. Please try again later."
            ) from exc

        return (
            guest_response.get("id")
            or guest_response.get("user_id")
            or (guest_response.get("user") or {}).get("user_id")
        )

    def get_waitlist_status(self) -> str:  # type: ignore[misc]
        return "Waitlist is not supported for Resy."

    def join_waitlist_queue(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        notes: str = "",
    ) -> str:
        return "Joining a waitlist is not supported for Resy."

    def get_user_wait_status(self) -> str:  # type: ignore[misc]
        return "User wait status is not supported for Resy."


def _format_phone_for_resy(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        raise RuntimeError("Phone number is required for Resy reservations.")

    if digits.startswith("1") and len(digits) == 11:
        normalized = digits
    elif len(digits) == 10:
        normalized = f"1{digits}"
    else:
        normalized = digits

    return f"+{normalized}"


def _normalize_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"1{digits}"
    return digits
