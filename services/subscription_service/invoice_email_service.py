import base64
from typing import Optional

from services import email_service
from utils.log import logger

# Postmark template ID for invoice email with analytics
INVOICE_WITH_ANALYTICS_TEMPLATE_ID = 42569088


def send_invoice_email_with_analytics(
    to_email: str,
    display_name: str,
    period_start: str,
    period_end: str,
    calls_handled: int,
    total_minutes: int,
    staff_hours_saved: int,
    pdf_content: bytes,
    pdf_filename: str,
    invoice_id: Optional[str] = None,
    from_email: Optional[str] = None,
    cc_emails: Optional[list[str]] = None,
    scope: str = "project",  # "project" or "account"
) -> dict:
    """
    Send an invoice email with usage analytics and PDF attachment.

    Supports both account-level and project-level invoices using the same template.

    Args:
        to_email: Recipient email address
        display_name: Display name (account name or project name)
        period_start: Start of billing period (e.g., "December 1")
        period_end: End of billing period (e.g., "December 31, 2025")
        calls_handled: Total number of calls handled
        total_minutes: Total call minutes
        staff_hours_saved: Estimated staff hours saved
        pdf_content: PDF file content as bytes
        pdf_filename: Name for the PDF attachment (e.g., "invoice_december_2025.pdf")
        invoice_id: Optional invoice ID for tracking
        from_email: Optional sender email (uses default if not provided)
        cc_emails: Optional CC recipients
        scope: Invoice scope - "project" for single project, "account" for all projects

    Returns:
        Dict: Postmark API response

    Raises:
        Exception: If email sending fails
    """
    try:
        # Encode PDF to base64
        pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")

        # Extract month and year from period_end (e.g., "December 31, 2025" -> "December 2025")
        # Handle formats like "December 31, 2025" or "Dec 31, 2025"
        month_year = period_end
        if "," in period_end:
            # Split by comma and take first part (month + day) and last part (year)
            parts = period_end.split(",")
            month_part = parts[0].strip().split()[0]  # Get just the month name
            year_part = parts[-1].strip()  # Get the year
            month_year = f"{month_part} {year_part}"

        # Prepare template model with all variables
        # Using generic "display_name" that works for both account and project
        template_model = {
            "product_name": "Palona AI",
            "display_name": display_name,
            "period_start": period_start,
            "period_end": period_end,
            "month_year": month_year,
            "calls_handled": str(calls_handled),
            "total_minutes": str(total_minutes),
            "staff_hours_saved": str(staff_hours_saved),
        }

        # Prepare attachment
        attachments = [
            {
                "Name": pdf_filename,
                "Content": pdf_base64,
                "ContentType": "application/pdf",
            }
        ]

        # Send email with template and attachment
        logger.info(
            f"Sending {scope}-level invoice email to {to_email} for {display_name} "
            f"covering {period_start} - {period_end}"
        )

        response = email_service.send_email_with_template(
            to_email=to_email,
            template_id=INVOICE_WITH_ANALYTICS_TEMPLATE_ID,
            template_model=template_model,
            from_email=from_email,
            cc_emails=cc_emails,
            tag=f"invoice-with-analytics-{scope}",
            attachments=attachments,
        )

        logger.info(
            f"Successfully sent {scope}-level invoice email to {to_email}",
            extra={
                "invoice_id": invoice_id,
                "display_name": display_name,
                "scope": scope,
                "message_id": response.get("MessageID"),
            },
        )

        return response

    except Exception as e:
        logger.error(
            f"Failed to send {scope}-level invoice email to {to_email}: {str(e)}",
            extra={
                "invoice_id": invoice_id,
                "display_name": display_name,
                "scope": scope,
                "error": str(e),
            },
        )
        raise
