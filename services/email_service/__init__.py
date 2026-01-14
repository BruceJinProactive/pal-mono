from typing import Dict, List, Optional

from . import _implementation


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
    attachments: Optional[List[Dict[str, str]]] = None,
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
        track_links (str): Link tracking preference ("None", "HtmlAndText", "HtmlOnly", "TextOnly")
        attachments (Optional[List[Dict[str, str]]]): List of attachments with Name, Content (base64), ContentType

    Returns:
        Dict: Postmark API response
    """
    return _implementation.send_email_with_template(
        to_email=to_email,
        template_id=template_id,
        template_model=template_model,
        from_email=from_email,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        reply_to=reply_to,
        tag=tag,
        track_opens=track_opens,
        track_links=track_links,
        attachments=attachments,
    )


def send_batch_emails_with_template(
    emails: List[Dict],
) -> Dict:
    """
    Send multiple emails using Postmark templates in a single API call.

    Args:
        emails (List[Dict]): List of email objects with the same structure as send_email_with_template

    Returns:
        Dict: Postmark API response with results for each email
    """
    return _implementation.send_batch_emails_with_template(emails)


def get_template_info(template_id: int) -> Dict:
    """
    Get information about a Postmark template.

    Args:
        template_id (int): Postmark template ID

    Returns:
        Dict: Template information from Postmark API
    """
    return _implementation.get_template_info(template_id)


def list_templates(count: int = 50, offset: int = 0) -> Dict:
    """
    List available Postmark templates.

    Args:
        count (int): Number of templates to return (max 100)
        offset (int): Number of templates to skip

    Returns:
        Dict: List of templates from Postmark API
    """
    return _implementation.list_templates(count=count, offset=offset)


__all__ = [
    "send_email_with_template",
    "send_batch_emails_with_template",
    "get_template_info",
    "list_templates",
]
