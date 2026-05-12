import base64
import uuid
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.billing import (
    BillingMetricsResponse,
    GenerateInvoiceRequest,
    GenerateInvoiceResponse,
    InvoiceActionRequest,
    InvoiceActionResponse,
    InvoiceLineItem,
    InvoiceResponse,
    ListInvoicesResponse,
    SendInvoiceEmailRequest,
    SendInvoiceEmailResponse,
    UpdatePaymentMethodRequest,
    UpdatePaymentMethodResponse,
)
from db.repositories.account_repository import AccountRepository
from db.repositories.analytics_repository import AnalyticsRepository
from db.repositories.project_repository import ProjectRepository
from services.subscription_service import (
    billing_service,
    invoice_email_service,
    stripe_invoice,
)
from utils.log import logger


async def update_payment_method(
    account_name: str,
    request: UpdatePaymentMethodRequest,
    context: UserContext,
    session: Session,
) -> UpdatePaymentMethodResponse:
    """
    Update the payment method for an account's subscription.

    Switches between:
    - 'autopay': Automatic credit card charges (default)
    - 'invoice': Manual invoicing with payment terms

    Args:
        account_name: Name of the account
        request: Payment method update request
        context: User context for authorization
        session: Database session

    Returns:
        UpdatePaymentMethodResponse: Updated payment method details

    Raises:
        HTTPException: 404 if account not found, 400 for invalid payment method
    """
    try:
        # Get account ID from name
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        # Update payment method
        result = billing_service.update_payment_method(
            session=session,
            account_id=account.id,
            payment_method=request.payment_method,
        )

        return UpdatePaymentMethodResponse(
            account_id=UUID(result["account_id"]),
            account_name=result["account_name"],
            payment_method=result["new_payment_method"],
            message=f"Payment method updated from {result['old_payment_method']} to {result['new_payment_method']}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error updating payment method: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update payment method",
        )


async def generate_invoice(
    account_name: str,
    request: GenerateInvoiceRequest,
    context: UserContext,
    session: Session,
) -> GenerateInvoiceResponse:
    """
    Manually generate and send an invoice for an account.

    This endpoint:
    1. Creates a draft invoice with all pending charges
    2. Finalizes the invoice
    3. Sends it to the customer via email

    Only works for accounts with payment_method='invoice'.

    Args:
        account_name: Name of the account
        request: Invoice generation request
        context: User context for authorization
        session: Database session

    Returns:
        GenerateInvoiceResponse: Generated invoice details

    Raises:
        HTTPException: 404 if account not found, 400 if account uses autopay
    """
    try:
        # Get account ID from name
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        # Generate invoice
        invoice_data = billing_service.generate_manual_invoice(
            session=session,
            account_id=account.id,
            billing_period=request.billing_period,
            days_until_due=request.days_until_due,
        )

        invoice_response = InvoiceResponse(
            invoice_id=invoice_data["invoice_id"],
            invoice_number=invoice_data.get("invoice_number"),
            status=invoice_data["status"],
            amount_due=invoice_data["amount_due"],
            currency=invoice_data["currency"],
            due_date=invoice_data.get("due_date"),
            invoice_url=invoice_data.get("invoice_url"),
            invoice_pdf=invoice_data.get("invoice_pdf"),
            line_items=[
                InvoiceLineItem(
                    description=item["description"],
                    amount=item["amount"],
                    currency=item["currency"],
                )
                for item in invoice_data.get("line_items", [])
            ],
        )

        return GenerateInvoiceResponse(
            invoice=invoice_response,
            message="Invoice generated and sent to customer",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error generating invoice: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate invoice",
        )


async def list_invoices(
    account_name: str,
    context: UserContext,
    session: Session,
    limit: int = 10,
    status: str | None = None,
) -> ListInvoicesResponse:
    """
    List invoices for an account.

    Args:
        account_name: Name of the account
        context: User context for authorization
        session: Database session
        limit: Maximum number of invoices to return (default: 10)
        status: Filter by status (draft, open, paid, void, uncollectible)

    Returns:
        ListInvoicesResponse: List of invoices

    Raises:
        HTTPException: 404 if account not found
    """
    try:
        # Get account ID from name
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        # Get invoices
        invoices_data = billing_service.get_account_invoices(
            session=session,
            account_id=account.id,
            limit=limit,
            status=status,
        )

        invoices = [
            InvoiceResponse(
                invoice_id=inv["invoice_id"],
                invoice_number=inv.get("invoice_number"),
                status=inv["status"],
                amount_due=inv["amount_due"],
                currency=inv["currency"],
                due_date=inv.get("due_date"),
                invoice_url=inv.get("invoice_url"),
                invoice_pdf=inv.get("invoice_pdf"),
                line_items=[
                    InvoiceLineItem(
                        description=item["description"],
                        amount=item["amount"],
                        currency=item["currency"],
                    )
                    for item in inv.get("line_items", [])
                ],
            )
            for inv in invoices_data
        ]

        return ListInvoicesResponse(
            invoices=invoices,
            total_count=len(invoices),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error listing invoices: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list invoices",
        )


async def finalize_invoice(
    account_name: str,
    request: InvoiceActionRequest,
    context: UserContext,
    session: Session,
) -> InvoiceActionResponse:
    """
    Finalize and send a draft invoice.

    This locks the invoice and emails it to the customer.

    Args:
        account_name: Name of the account
        request: Invoice action request with invoice_id
        context: User context for authorization
        session: Database session

    Returns:
        InvoiceActionResponse: Action result

    Raises:
        HTTPException: 404 if account not found, 400 if not authorized
    """
    try:
        # Get account ID from name
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        # Finalize invoice
        result = billing_service.finalize_invoice(
            session=session,
            account_id=account.id,
            invoice_id=request.invoice_id,
        )

        return InvoiceActionResponse(
            invoice_id=result["invoice_id"],
            status=result["status"],
            message=result["message"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error finalizing invoice: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize invoice",
        )


async def void_invoice(
    account_name: str,
    request: InvoiceActionRequest,
    context: UserContext,
    session: Session,
) -> InvoiceActionResponse:
    """
    Void (cancel) an invoice.

    Args:
        account_name: Name of the account
        request: Invoice action request with invoice_id
        context: User context for authorization
        session: Database session

    Returns:
        InvoiceActionResponse: Action result

    Raises:
        HTTPException: 404 if account not found, 400 if not authorized
    """
    try:
        # Get account ID from name
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        # Void invoice
        result = billing_service.cancel_invoice(
            session=session,
            account_id=account.id,
            invoice_id=request.invoice_id,
        )

        return InvoiceActionResponse(
            invoice_id=result["invoice_id"],
            status=result["status"],
            message=result["message"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error voiding invoice: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to void invoice",
        )


async def send_account_invoice_email(
    account_name: str,
    request: SendInvoiceEmailRequest,
    context: UserContext,
    session: Session,
) -> SendInvoiceEmailResponse:
    """
    Send an account-level invoice email with combined usage analytics and PDF attachment.

    Args:
        account_name: Name of the account
        request: Email details including combined analytics and PDF
        context: User context for authorization
        session: Database session

    Returns:
        SendInvoiceEmailResponse: Email send result

    Raises:
        HTTPException: 404 if account not found, 500 if email send fails
    """
    try:
        # Validate account exists
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_name}' not found",
            )

        # Validate that either pdf_base64 or stripe_invoice_id is provided
        if not request.pdf_base64 and not request.stripe_invoice_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either pdf_base64 or stripe_invoice_id must be provided",
            )

        # Get PDF content
        if request.stripe_invoice_id:
            # Fetch PDF from Stripe
            try:
                pdf_content = stripe_invoice.get_invoice_pdf(request.stripe_invoice_id)
                pdf_filename = (
                    request.pdf_filename or f"invoice_{request.stripe_invoice_id}.pdf"
                )
                logger.info(
                    f"Fetched invoice PDF from Stripe: {request.stripe_invoice_id}"
                )
            except ValueError as e:
                logger.error(f"Failed to fetch Stripe invoice PDF: {e}")
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to fetch Stripe invoice: {str(e)}",
                )
        elif request.pdf_base64:
            # Decode PDF from base64
            try:
                pdf_content = base64.b64decode(request.pdf_base64)
                pdf_filename = request.pdf_filename or "invoice.pdf"
            except Exception as e:
                logger.error(f"Failed to decode PDF base64: {e}")
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Invalid PDF base64 encoding",
                )
        else:
            # This should never happen due to earlier validation, but for type safety
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either pdf_base64 or stripe_invoice_id must be provided",
            )

        # Send the email for account-level invoice
        result = invoice_email_service.send_invoice_email_with_analytics(
            to_email=request.to_email,
            display_name=account.display_name or account.name,
            period_start=request.period_start,
            period_end=request.period_end,
            calls_handled=request.calls_handled,
            total_minutes=request.total_minutes,
            staff_hours_saved=request.staff_hours_saved,
            pdf_content=pdf_content,
            pdf_filename=pdf_filename,
            cc_emails=request.cc_emails,
            scope="account",
            template_id=request.template_id,
        )

        logger.info(
            f"Successfully sent account-level invoice email to {request.to_email} for {account_name}",
            extra={
                "account_name": account_name,
                "message_id": result.get("MessageID"),
            },
        )

        return SendInvoiceEmailResponse(
            success=True,
            message=f"Invoice email sent successfully to {request.to_email}",
            message_id=result.get("MessageID"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending account invoice email: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send invoice email: {str(e)}",
        )


async def send_project_invoice_email(
    account_name: str,
    project_id: UUID,
    request: SendInvoiceEmailRequest,
    context: UserContext,
    session: Session,
) -> SendInvoiceEmailResponse:
    """
    Send a project-level invoice email with usage analytics and PDF attachment.

    Args:
        account_name: Name of the account
        project_id: UUID of the project
        request: Email details including analytics and PDF
        context: User context for authorization
        session: Database session

    Returns:
        SendInvoiceEmailResponse: Email send result

    Raises:
        HTTPException: 404 if account/project not found, 500 if email send fails
    """
    try:
        # Validate account exists
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_name}' not found",
            )

        # Validate project exists and belongs to account
        project_repo = ProjectRepository(session)
        project = project_repo.get_project(project_id)
        if not project or project.account_id != account.id:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' not found in account '{account_name}'",
            )

        # Validate that either pdf_base64 or stripe_invoice_id is provided
        if not request.pdf_base64 and not request.stripe_invoice_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either pdf_base64 or stripe_invoice_id must be provided",
            )

        # Get PDF content
        if request.stripe_invoice_id:
            # Fetch PDF from Stripe
            try:
                pdf_content = stripe_invoice.get_invoice_pdf(request.stripe_invoice_id)
                pdf_filename = (
                    request.pdf_filename or f"invoice_{request.stripe_invoice_id}.pdf"
                )
                logger.info(
                    f"Fetched invoice PDF from Stripe: {request.stripe_invoice_id}"
                )
            except ValueError as e:
                logger.error(f"Failed to fetch Stripe invoice PDF: {e}")
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to fetch Stripe invoice: {str(e)}",
                )
        elif request.pdf_base64:
            # Decode PDF from base64
            try:
                pdf_content = base64.b64decode(request.pdf_base64)
                pdf_filename = request.pdf_filename or "invoice.pdf"
            except Exception as e:
                logger.error(f"Failed to decode PDF base64: {e}")
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Invalid PDF base64 encoding",
                )
        else:
            # This should never happen due to earlier validation, but for type safety
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either pdf_base64 or stripe_invoice_id must be provided",
            )

        # Send the email with combined account + project display name
        account_display = account.display_name or account.name
        project_display = project.display_name or project.name
        combined_display_name = f"{account_display} {project_display}"

        result = invoice_email_service.send_invoice_email_with_analytics(
            to_email=request.to_email,
            display_name=combined_display_name,
            period_start=request.period_start,
            period_end=request.period_end,
            calls_handled=request.calls_handled,
            total_minutes=request.total_minutes,
            staff_hours_saved=request.staff_hours_saved,
            pdf_content=pdf_content,
            pdf_filename=pdf_filename,
            cc_emails=request.cc_emails,
            scope="project",
            template_id=request.template_id,
        )

        logger.info(
            f"Successfully sent invoice email to {request.to_email} for project {project.name}",
            extra={
                "account_name": account_name,
                "project_id": str(project_id),
                "project_name": project.name,
                "message_id": result.get("MessageID"),
            },
        )

        return SendInvoiceEmailResponse(
            success=True,
            message=f"Invoice email sent successfully to {request.to_email}",
            message_id=result.get("MessageID"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending invoice email: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send invoice email: {str(e)}",
        )


def get_billing_metrics(
    account_name: str,
    start_date: str,
    end_date: str,
    context: UserContext,
    session: Session,
) -> BillingMetricsResponse:
    """
    Get billing metrics (calls, orders, reservations) for an account over a date range.

    Args:
        account_name: Name of the account
        start_date: Billing period start (ISO date string)
        end_date: Billing period end (ISO date string)
        context: User context for authorization
        session: Database session

    Returns:
        BillingMetricsResponse: Billing metrics for the account

    Raises:
        HTTPException: 404 if account not found, 400 for invalid dates
    """
    try:
        # Parse dates
        try:
            parsed_start = datetime.fromisoformat(start_date)
            parsed_end = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use ISO date format (e.g. 2026-04-01)",
            )

        if parsed_start > parsed_end:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before end_date",
            )

        # Set end_date to end-of-day to include the full final day
        parsed_end = parsed_end.replace(hour=23, minute=59, second=59)

        # Get account
        account_repo = AccountRepository(session)
        account = account_repo.get_account(account_name)
        if not account:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Account {account_name} not found",
            )

        analytics_repo = AnalyticsRepository(session)
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] = {"account_id": account.id}

        # Call metrics (total_calls, avg_duration, ...)
        call_data = analytics_repo.get_calls_time_summary(
            start_date=parsed_start,
            end_date=parsed_end,
            group_by=[],
            filter_by=filter_by,
        )
        total_calls = int(call_data[0][0]) if call_data else 0
        avg_duration = float(call_data[0][1]) if call_data and call_data[0][1] else 0.0

        # Conversion metrics (total_conversations, conversations_with_orders,
        # paid_orders, total_subtotal, paid_total, total_reservations, total_waitlists)
        conversion_data = analytics_repo.get_conversion_summary(
            start_date=parsed_start,
            end_date=parsed_end,
            group_by=[],
            filter_by=filter_by,
        )
        paid_orders = int(conversion_data[0][2]) if conversion_data else 0
        paid_total = (
            float(conversion_data[0][4])
            if conversion_data and conversion_data[0][4]
            else 0.0
        )
        total_reservations = int(conversion_data[0][5]) if conversion_data else 0

        # Determine template variant based on activity
        has_orders = paid_orders > 0
        has_reservations = total_reservations > 0
        if has_orders and has_reservations:
            template_variant = "ordering_reservation"
            template_id = 44949424
        elif has_orders:
            template_variant = "ordering"
            template_id = 44949422
        elif has_reservations:
            template_variant = "reservation"
            template_id = 44949423
        else:
            template_variant = "answering"
            template_id = 42569088

        return BillingMetricsResponse(
            account_name=account_name,
            period_start=start_date,
            period_end=end_date,
            total_calls=total_calls,
            avg_call_duration_seconds=round(avg_duration, 1),
            total_reservations=total_reservations,
            total_orders=paid_orders,
            order_total_dollars=round(paid_total, 2),
            template_variant=template_variant,
            template_id=template_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting billing metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get billing metrics",
        )
