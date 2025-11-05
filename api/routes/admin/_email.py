from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.schemas.admin.email import (
    GetTemplateInfoRequest,
    ListTemplatesRequest,
    SendBatchEmailsRequest,
    SendEmailRequest,
)
from services import email_service
from services.auth_types import UserContext
from utils.log import logger


async def send_email(
    request: SendEmailRequest,
    context: UserContext,
    session: Session,
):
    """
    Send a single email using a Postmark template.
    """

    logger.info(
        "Attempting to send email with template",
        extra={
            "to_email": request.to_email,
            "template_id": request.template_id,
            "user_email": context.email,
        },
    )

    try:
        response = email_service.send_email_with_template(
            to_email=request.to_email,
            template_id=request.template_id,
            template_model=request.template_model,
            from_email=request.from_email,
            cc_emails=request.cc_emails,
            bcc_emails=request.bcc_emails,
            reply_to=request.reply_to,
            tag=request.tag,
            track_opens=request.track_opens,
            track_links=request.track_links,
        )
    except Exception as err:
        logger.exception("Failed to send email with template")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {err}",
        )

    logger.info(
        "Successfully sent email with template",
        extra={
            "to_email": request.to_email,
            "template_id": request.template_id,
            "message_id": response.get("MessageID"),
        },
    )

    return response


async def send_batch_emails(
    request: SendBatchEmailsRequest,
    context: UserContext,
    session: Session,
):
    """
    Send multiple emails using Postmark templates in a single API call.
    """

    logger.info(
        "Attempting to send batch emails with templates",
        extra={
            "email_count": len(request.emails),
            "user_email": context.email,
        },
    )

    try:
        # Convert the request models to dictionaries for the service
        emails_data = []
        for email_request in request.emails:
            emails_data.append(
                {
                    "to_email": email_request.to_email,
                    "template_id": email_request.template_id,
                    "template_model": email_request.template_model,
                    "from_email": email_request.from_email,
                    "cc_emails": email_request.cc_emails,
                    "bcc_emails": email_request.bcc_emails,
                    "reply_to": email_request.reply_to,
                    "tag": email_request.tag,
                    "track_opens": email_request.track_opens,
                    "track_links": email_request.track_links,
                }
            )

        response = email_service.send_batch_emails_with_template(emails_data)
    except Exception as err:
        logger.exception("Failed to send batch emails with templates")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send batch emails: {err}",
        )

    logger.info(
        "Successfully sent batch emails with templates",
        extra={
            "email_count": len(request.emails),
            "batch_id": response.get("batch_id"),
        },
    )

    return response


async def get_template_info(
    request: GetTemplateInfoRequest,
    context: UserContext,
    session: Session,
):
    """
    Get information about a Postmark template.
    """

    logger.info(
        "Attempting to get template info",
        extra={
            "template_id": request.template_id,
            "user_email": context.email,
        },
    )

    try:
        response = email_service.get_template_info(request.template_id)
    except Exception as err:
        logger.exception("Failed to get template info")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get template info: {err}",
        )

    logger.info(
        "Successfully retrieved template info",
        extra={
            "template_id": request.template_id,
            "template_name": response.get("Name"),
        },
    )

    return response


async def list_templates(
    request: ListTemplatesRequest,
    context: UserContext,
    session: Session,
):
    """
    List available Postmark templates.
    """

    logger.info(
        "Attempting to list templates",
        extra={
            "count": request.count,
            "offset": request.offset,
            "user_email": context.email,
        },
    )

    try:
        response = email_service.list_templates(
            count=request.count,
            offset=request.offset,
        )
    except Exception as err:
        logger.exception("Failed to list templates")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list templates: {err}",
        )

    logger.info(
        "Successfully listed templates",
        extra={
            "count": request.count,
            "offset": request.offset,
            "total_count": response.get("TotalCount"),
        },
    )

    return response
