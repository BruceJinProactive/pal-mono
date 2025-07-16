import http.client
import json
import os
from typing import Dict, List, Optional, Union

from utils import secret
from utils.log import logger

# Postmark API configuration
POSTMARK_API_HOST = "api.postmarkapp.com"
DEFAULT_TIMEOUT = 30  # 30 seconds default timeout
DEFAULT_FROM_EMAIL = "support@proactiveailab.com"  # Default sender email


def _get_postmark_token() -> str:
    """Get Postmark server token from AWS Secret Manager."""
    try:
        # First try to get from environment variable (for local development)
        token = os.getenv("POSTMARK_SERVER_TOKEN")
        if token:
            return token

        # If not in environment, get from AWS Secret Manager
        app_secrets = secret._get_client_secrets()
        token = app_secrets.get("POSTMARK_SERVER_TOKEN")

        if not token:
            raise ValueError(
                "POSTMARK_SERVER_TOKEN not found in environment or AWS Secret Manager"
            )

        return token
    except Exception as e:
        logger.error(
            f"[EmailService._get_postmark_token] Failed to get Postmark token: {str(e)}"
        )
        raise ValueError(f"Failed to get POSTMARK_SERVER_TOKEN: {str(e)}")


def _make_postmark_request(
    endpoint: str,
    method: str = "POST",
    payload: Optional[Union[Dict, List]] = None,
    query_params: Optional[Dict[str, str]] = None,
) -> Dict:
    """
    Make a request to the Postmark API.

    Args:
        endpoint (str): API endpoint (e.g., "/email/withTemplate")
        method (str): HTTP method (GET, POST)
        payload (Optional[Union[Dict, List]]): Request payload for POST requests
        query_params (Optional[Dict[str, str]]): Query parameters for GET requests

    Returns:
        Dict: API response data

    Raises:
        Exception: If the API request fails
    """
    token = _get_postmark_token()

    # Build query string if provided
    path = endpoint
    if query_params:
        from urllib.parse import urlencode

        path += "?" + urlencode(query_params)

    # Prepare headers
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": token,
    }

    # Prepare request body
    request_body = ""
    if payload:
        request_body = json.dumps(payload)

    logger.debug(
        f"[EmailService._make_postmark_request] Calling Postmark API: {method} {path} | "
        f"Payload: {payload}"
    )

    try:
        conn = http.client.HTTPSConnection(POSTMARK_API_HOST, timeout=DEFAULT_TIMEOUT)
        conn.request(method, path, request_body, headers=headers)

        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # Parse JSON response
        try:
            decoded_body = json.loads(response_data) if response_data else {}
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response: {response_data}")
            decoded_body = {"raw_content": response_data}

        logger.debug(
            f"[EmailService._make_postmark_request] Response: {response.status} - {response.reason}"
        )

        # Handle non-200 responses
        if response.status != 200:
            error_msg = f"Postmark API error: {response.status} - {response.reason}"
            if decoded_body:
                error_msg += f" - {decoded_body}"
            raise Exception(error_msg)

        return decoded_body

    except Exception as e:
        logger.error(f"[EmailService._make_postmark_request] Error: {str(e)}")
        raise
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()


def send_email_with_template(
    to_email: str,
    template_id: int,
    template_model: Dict[str, str],
    from_email: Optional[str] = None,
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    tag: Optional[str] = None,
    track_opens: bool = True,
    track_links: str = "HtmlAndText",
) -> Dict:
    """
    Send an email using a Postmark template.

    Args:
        to_email (str): Recipient email address
        template_id (int): Postmark template ID
        template_model (Dict[str, str]): Template variables
        from_email (Optional[str]): Sender email address (uses default if not provided)
        cc_emails (Optional[List[str]]): CC recipient email addresses
        bcc_emails (Optional[List[str]]): BCC recipient email addresses
        reply_to (Optional[str]): Reply-to email address
        tag (Optional[str]): Email tag for tracking
        track_opens (bool): Whether to track email opens
        track_links (str): Link tracking preference

    Returns:
        Dict: Postmark API response
    """
    # Use default from email if not provided
    sender_email = from_email or DEFAULT_FROM_EMAIL

    # Build payload
    payload = {
        "From": sender_email,
        "To": to_email,
        "TemplateId": template_id,
        "TemplateModel": template_model,
        "TrackOpens": track_opens,
        "TrackLinks": track_links,
    }

    # Add optional fields
    if cc_emails:
        payload["Cc"] = ",".join(cc_emails)
    if bcc_emails:
        payload["Bcc"] = ",".join(bcc_emails)
    if reply_to:
        payload["ReplyTo"] = reply_to
    if tag:
        payload["Tag"] = tag

    logger.info(
        f"[EmailService.send_email_with_template] Sending email to {to_email} "
        f"using template {template_id}"
    )

    return _make_postmark_request("/email/withTemplate", payload=payload)


def send_batch_emails_with_template(
    emails: List[Dict],
) -> Dict:
    """
    Send multiple emails using Postmark templates by making individual API calls.

    Args:
        emails (List[Dict]): List of email objects with the same structure as send_email_with_template

    Returns:
        Dict: Combined results from all email sends
    """
    results = []
    success_count = 0
    error_count = 0

    logger.info(
        f"[EmailService.send_batch_emails_with_template] Sending batch of {len(emails)} emails"
    )

    for i, email in enumerate(emails):
        try:
            # Use default from email if not provided
            if "from_email" not in email or not email["from_email"]:
                email["from_email"] = DEFAULT_FROM_EMAIL

            # Send individual email
            result = send_email_with_template(
                to_email=email["to_email"],
                template_id=email["template_id"],
                template_model=email["template_model"],
                from_email=email["from_email"],
                cc_emails=email.get("cc_emails"),
                bcc_emails=email.get("bcc_emails"),
                reply_to=email.get("reply_to"),
                tag=email.get("tag"),
                track_opens=email.get("track_opens", True),
                track_links=email.get("track_links", "HtmlAndText"),
            )

            results.append(
                {"index": i, "success": True, "result": result, "error": None}
            )
            success_count += 1

        except Exception as e:
            logger.error(
                f"[EmailService.send_batch_emails_with_template] Failed to send email {i}: {str(e)}"
            )
            results.append(
                {"index": i, "success": False, "result": None, "error": str(e)}
            )
            error_count += 1

    logger.info(
        f"[EmailService.send_batch_emails_with_template] Batch complete: "
        f"{success_count} successful, {error_count} failed"
    )

    return {
        "batch_id": f"batch_{len(emails)}_{success_count}_{error_count}",
        "total_count": len(emails),
        "success_count": success_count,
        "error_count": error_count,
        "results": results,
    }


def get_template_info(template_id: int) -> Dict:
    """
    Get information about a Postmark template.

    Args:
        template_id (int): Postmark template ID

    Returns:
        Dict: Template information from Postmark API
    """
    logger.info(
        f"[EmailService.get_template_info] Getting info for template {template_id}"
    )

    return _make_postmark_request(f"/templates/{template_id}", method="GET")


def list_templates(count: int = 50, offset: int = 0) -> Dict:
    """
    List available Postmark templates.

    Args:
        count (int): Number of templates to return (max 100)
        offset (int): Number of templates to skip

    Returns:
        Dict: List of templates from Postmark API
    """
    # Validate count parameter
    if count > 100:
        count = 100
    elif count < 1:
        count = 1

    query_params = {
        "count": str(count),
        "offset": str(offset),
    }

    logger.info(
        f"[EmailService.list_templates] Listing templates (count: {count}, offset: {offset})"
    )

    return _make_postmark_request("/templates", method="GET", query_params=query_params)
