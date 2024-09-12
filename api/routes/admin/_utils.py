from fastapi import HTTPException, Request


async def retrieve_body_message(request: Request) -> str:
    """
    Retrieves the 'message' field to be injected into a Message object.

    Args:
        request (Request): The FastAPI request object containing the JSON body to validate.

    Returns:
        str: The validated 'message' field from the request body.

    Raises:
        HTTPException: If the 'message' field is missing or not a string, or if there is
                       an error in processing the request body.
    """
    body = await request.json()
    try:
        body_message = body["message"]
        if not isinstance(body_message, str):
            raise HTTPException(
                status_code=422,
                detail="Validation error: 'message' must be a string",
            )
        return body_message
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"Validation error: 'message' field is required\n\nInvalid request body: {body}",
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=422,  # Unprocessable Entity
            detail=f"Validation error: {e}\n\nInvalid request body: {body}",
        )
