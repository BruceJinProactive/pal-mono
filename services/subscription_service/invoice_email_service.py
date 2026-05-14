import base64
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe

from db.repositories.account_repository import AccountRepository
from db.repositories.analytics_repository import AnalyticsRepository
from db.session import SyncSessionLocal
from services import email_service
from services.subscription_service import stripe_invoice
from utils.log import logger
from utils.phone import get_test_phone_numbers

# Postmark template IDs for invoice emails based on activity
TEMPLATE_ID_ANSWERING = 42569088
TEMPLATE_ID_ORDERING = 44949422
TEMPLATE_ID_RESERVATION = 44949423
TEMPLATE_ID_ORDERING_RESERVATION = 44949424

# Backwards-compatible alias
INVOICE_WITH_ANALYTICS_TEMPLATE_ID = TEMPLATE_ID_ANSWERING

# Average call duration assumption for staff hours estimate (minutes)
_AVG_CALL_DURATION_MINUTES = 3

# Company tax identifier
TAX_ID = "US EIN 99-1555916"


def _select_template_id(total_orders: int, total_reservations: int) -> int:
    """Choose the Postmark template based on what activity occurred."""
    has_orders = total_orders > 0
    has_reservations = total_reservations > 0
    if has_orders and has_reservations:
        return TEMPLATE_ID_ORDERING_RESERVATION
    elif has_orders:
        return TEMPLATE_ID_ORDERING
    elif has_reservations:
        return TEMPLATE_ID_RESERVATION
    return TEMPLATE_ID_ANSWERING


def send_automated_invoice_email(
    finalized_invoice_id: str,
    stripe_customer_id: str,
) -> None:
    """
    Automatically send the analytics email after a billing-period invoice is finalized.

    Retrieves billing period from the Stripe invoice, queries internal analytics
    for that period, selects the appropriate template, fetches the invoice PDF,
    and sends the email to the account's notification address.

    This is called from the invoice.created webhook after finalizing the previous
    period's draft invoice.
    """
    try:
        # 1. Retrieve the finalized invoice from Stripe to get period dates
        inv = stripe.Invoice.retrieve(finalized_invoice_id)
        period_start_ts: int | None = getattr(inv, "period_start", None)
        period_end_ts: int | None = getattr(inv, "period_end", None)

        if not period_start_ts or not period_end_ts:
            logger.warning(
                "[Invoice Email] Cannot send analytics email — invoice missing period dates",
                extra={"invoice_id": finalized_invoice_id},
            )
            return

        period_start_dt = datetime.fromtimestamp(period_start_ts, tz=timezone.utc)
        period_end_dt = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)

        # 2. Look up account by stripe_customer_id
        with SyncSessionLocal() as session:
            account_repo = AccountRepository(session)
            account = account_repo.get_account_by_stripe_customer_id(stripe_customer_id)

            if not account:
                logger.warning(
                    "[Invoice Email] No account found for Stripe customer — skipping email",
                    extra={
                        "invoice_id": finalized_invoice_id,
                        "stripe_customer_id": stripe_customer_id,
                    },
                )
                return

            to_email = account.notification_email
            if not to_email:
                logger.info(
                    "[Invoice Email] Account has no notification_email — skipping",
                    extra={
                        "invoice_id": finalized_invoice_id,
                        "account_name": account.name,
                    },
                )
                return

            display_name = account.display_name or account.name
            account_id: uuid.UUID = account.id

            # 3. Query analytics for the billing period
            analytics_repo = AnalyticsRepository(session)
            filter_by: dict[str, uuid.UUID | list[uuid.UUID]] = {
                "account_id": account_id
            }

            # Get test phone numbers to exclude from billing analytics
            test_numbers = list(get_test_phone_numbers())

            # Extend end date to end-of-day
            query_end = period_end_dt.replace(hour=23, minute=59, second=59)

            call_data = analytics_repo.get_calls_time_summary(
                start_date=period_start_dt,
                end_date=query_end,
                group_by=[],
                filter_by=filter_by,
                exclude_eval_calls=True,
                exclude_caller_numbers=test_numbers or None,
            )
            total_calls = int(call_data[0][0]) if call_data else 0
            avg_duration = (
                float(call_data[0][1]) if call_data and call_data[0][1] else 0.0
            )
            total_minutes = round(total_calls * avg_duration / 60)

            conversion_data = analytics_repo.get_conversion_summary(
                start_date=period_start_dt,
                end_date=query_end,
                group_by=[],
                filter_by=filter_by,
                exclude_eval_calls=True,
                exclude_caller_numbers=test_numbers or None,
            )
            paid_orders = int(conversion_data[0][2]) if conversion_data else 0
            paid_total = (
                float(conversion_data[0][4])
                if conversion_data and conversion_data[0][4]
                else 0.0
            )
            total_reservations = int(conversion_data[0][5]) if conversion_data else 0

        # 4. Compute derived metrics
        staff_hours_saved = round(total_calls * _AVG_CALL_DURATION_MINUTES / 60)
        template_id = _select_template_id(paid_orders, total_reservations)

        # 5. Fetch invoice PDF from Stripe
        try:
            pdf_content = stripe_invoice.get_invoice_pdf(finalized_invoice_id)
        except Exception as e:
            logger.error(
                "[Invoice Email] Failed to fetch invoice PDF — skipping email",
                extra={
                    "invoice_id": finalized_invoice_id,
                    "error": str(e),
                },
            )
            return

        # 6. Format period strings for the email template
        period_start_str = f"{period_start_dt.strftime('%B')} {period_start_dt.day}"
        period_end_str = (
            f"{period_end_dt.strftime('%B')} {period_end_dt.day}, {period_end_dt.year}"
        )
        billing_period_str = (
            f"{period_start_dt.strftime('%m/%d/%Y')} - "
            f"{period_end_dt.strftime('%m/%d/%Y')}"
        )
        pdf_filename = (
            f"invoice_{period_start_dt.strftime('%B').lower()}"
            f"_{period_start_dt.year}.pdf"
        )

        # 7. Send the email
        send_invoice_email_with_analytics(
            to_email=to_email,
            display_name=display_name,
            period_start=period_start_str,
            period_end=period_end_str,
            calls_handled=total_calls,
            total_minutes=total_minutes,
            staff_hours_saved=staff_hours_saved,
            pdf_content=pdf_content,
            pdf_filename=pdf_filename,
            invoice_id=finalized_invoice_id,
            scope="account",
            template_id=template_id,
            total_orders=paid_orders,
            order_total_dollars=paid_total,
            total_reservations=total_reservations,
            billing_period=billing_period_str,
        )

        logger.info(
            "[Invoice Email] Automated analytics email sent successfully",
            extra={
                "invoice_id": finalized_invoice_id,
                "account_name": display_name,
                "template_id": template_id,
                "total_calls": total_calls,
                "total_orders": paid_orders,
                "total_reservations": total_reservations,
            },
        )

    except Exception as e:
        # Don't let email failures break the webhook flow
        logger.error(
            "[Invoice Email] Failed to send automated analytics email",
            extra={
                "invoice_id": finalized_invoice_id,
                "stripe_customer_id": stripe_customer_id,
                "error": str(e),
            },
        )


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
    template_id: Optional[int] = None,
    total_orders: int = 0,
    order_total_dollars: float = 0.0,
    total_reservations: int = 0,
    billing_period: str = "",
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
            "billing_period": billing_period if billing_period else "",
            "month_year": month_year,
            "calls_handled": str(calls_handled),
            "total_minutes": str(total_minutes),
            "staff_hours_saved": str(staff_hours_saved),
            "total_orders": str(total_orders),
            "order_total_dollars": f"{order_total_dollars:.2f}",
            "total_reservations": str(total_reservations),
            "tax_id": TAX_ID,
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

        resolved_template_id = (
            template_id
            if template_id is not None
            else INVOICE_WITH_ANALYTICS_TEMPLATE_ID
        )

        response = email_service.send_email_with_template(
            to_email=to_email,
            template_id=resolved_template_id,
            template_model=template_model,
            from_email=from_email,
            cc_emails=cc_emails,
            bcc_emails=["notifications@proactiveailab.com", "notifications@palona.ai"],
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
