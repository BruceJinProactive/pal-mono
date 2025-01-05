import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from services.admin_service import (
    deauthorize_instagram_access_token,
    get_instagram_connected,
    get_instagram_username,
    remove_instagram_access_token,
    set_instagram_access_token,
)

from . import _auth, _utils


async def connect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    ig_access_token = request.headers.get("Access-Token", "")
    ig_user_id = request.headers.get("User-Id", "")
    ig_username = request.headers.get("Username", "")

    if not all([ig_access_token, ig_user_id, ig_username]):
        raise HTTPException(
            status_code=400,
            detail="Missing required header(s): Access-Token, Username and/or User-Id",
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        set_instagram_access_token(
            session, project_uuid, ig_access_token, ig_user_id, ig_username
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account connected"}


async def disconnect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        remove_instagram_access_token(session, project_uuid)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account disconnected"}


async def get_project_instagram_connected(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        connected = get_instagram_connected(session, project_uuid)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"connected": connected}


async def get_project_instagram_username(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    # Verify the project is connected to instagram
    try:
        connected = get_instagram_connected(session, project_uuid)
        if not connected:
            raise HTTPException(
                status_code=404,
                detail="Project not connected to Instagram",
                headers={"Content-Type": "application/json"},
            )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    try:
        username = get_instagram_username(session, project_uuid)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Project not connected to Instagram",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"username": username}


async def handle_instagram_deauthorization(
    ig_user_id: str, request: Request, session: Session = Depends(db.get_db)
):
    encoded_signature = request.headers.get("Encoded-Signature", "")
    encoded_payload = request.headers.get("Encoded-Payload", "")

    # Check for missing headers
    if not all([encoded_signature, encoded_payload]):
        raise HTTPException(
            status_code=400,
            detail="Missing required headers: Encoded-Signature and/or Encoded-Payload",
            headers={"Content-Type": "application/json"},
        )

    # Verify the incoming request
    try:
        _utils.verify_instagram_deauthorize_signature(
            encoded_payload, encoded_signature
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        deauthorize_instagram_access_token(session, ig_user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account deauthorized"}


async def read_projects(request: Request, session: Session = Depends(db.get_db)):
    account = _auth.get_account_from_id_token(request, session)
    return JSONResponse(jsonable_encoder(account.projects))
