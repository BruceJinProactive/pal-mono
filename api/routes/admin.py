import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api.routes.endpoints import endpoints
from app.auth import parse_admin_console_id_token
from services.admin_service import create_account_with_defaults, get_assistant_data

######################################################
## Router for Admin Console
######################################################

"""
NOTE: 
- This code is a work in progress. The rest of the implementation will be done with a fast-follow.
- Only code with complete Python Docstrings are complete.
"""


admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])


@admin_router.post("/create_account")
def create_account(request: Request):
    """
    This endpoint is used to create an account in the database.
    Without the account in the database, the rest of the functionality will not work.

    Args:
        request (Request): The request object containing the headers and other request data.

    Returns:
        str: A JSON string indicating that the account has been created.
    """
    decrypted_id_token = parse_admin_console_id_token(
        request.headers.get("Authorization")
    )
    create_account_with_defaults(decrypted_id_token["custom:account_name"])
    return '{"message": "Account created"}'


@admin_router.get("/account")
def read_account(request: Request):
    decrypted_id_token = parse_admin_console_id_token(
        request.headers.get("Authorization")
    )
    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/inbox")
def read_inbox(request: Request):
    # TODO: @ilbum fast-follow with decoupling auth from streamlit, add authorization
    # 1. Check admin level
    # 2. Check organization
    # 3. Get inbox messages
    chat_data = [
        {
            "chatId": 36478232,
            "lastMessage": "A professional dreads deadlines",
            "numMessages": 85,
        },
        {
            "chatId": 47593205,
            "lastMessage": "A parent proud at graduation",
            "numMessages": 164,
        },
        {
            "chatId": 75892945,
            "lastMessage": "An artist inspired by sunset",
            "numMessages": 1100,
        },
        {
            "chatId": 46284652,
            "lastMessage": "A teacher satisfied by a lesson",
            "numMessages": 19,
        },
        {
            "chatId": 18402851,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402852,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402853,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402854,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402855,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402856,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402857,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
        {
            "chatId": 18402858,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
    ]
    return JSONResponse(content=chat_data)


@admin_router.get("/chat")
def read_chat(request: Request):
    # TODO: @ilbum fast-follow with decoupling auth from streamlit
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token is expired",
            headers={"Content-Type": "application/json"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=401,
            detail="Token was not issued for this audience",
            headers={"Content-Type": "application/json"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {e}",
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"Content-Type": "application/json"},
        )

    unformatted_assistant_data = get_assistant_data(
        decrypted_id_token["custom:account_name"]
    )

    return unformatted_assistant_data[0].memory["chat_history"]


@admin_router.get("/knowledge")
def read_knowledge(request: Request):
    # TODO: @ilbum fast-follow with decoupling auth from streamlit

    knowledge_base_json = {
        "profile": {
            "company": "Proactive AI Lab",
            "email": "agent@proactiveailab.com",
            "phone": "555-555-5555",
            "website": "https://www.proactiveailab.com",
        },
        "branding": "Our AI agent is designed to emulate a real person, utilizing a new generation of AI systems with multi-agents and multimodal-to-action models, enhancing its high EQ language capabilities.",
        "prompt": "You're name is Anna and you are a highly emotionally intelligent executive assistant.\n\n - You have expertise in coding.\n - You have expertise in customer service.\n - You have expertise in sales and marketing.",
        "terms_&_faq": "Once upon a time, in a bustling tech hub, a team of passionate innovators embarked on a remarkable journey to revolutionize customer interactions. Their vision? To create an advanced AI system equipped with multi-agents and multimodal-to-action models, complemented by a cutting-edge high EQ language model. With unwavering determination, they set out to empower businesses worldwide, enabling them to provide unparalleled levels of personalized customer experiences, seamless automation, and unmatched operational efficiency. This is the inspiring founder story behind the groundbreaking technology that is reshaping the future of customer engagement.",
    }

    return knowledge_base_json


# This renders the "Users" page in the Admin Console.
# This page is used to view all the "consumers" for the "client" (organization).
#   Example: Max's Coffee's customers.
@admin_router.get("/users")
def read_users(request: Request):
    # TODO: @ilbum fast-follow with decoupling auth from streamlit
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token is expired",
            headers={"Content-Type": "application/json"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=401,
            detail="Token was not issued for this audience",
            headers={"Content-Type": "application/json"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {e}",
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"Content-Type": "application/json"},
        )

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/campaigns")
def read_campaigns(request: Request):
    # TODO: @ilbum fast-follow with decoupling auth from streamlit
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token is expired",
            headers={"Content-Type": "application/json"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=401,
            detail="Token was not issued for this audience",
            headers={"Content-Type": "application/json"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {e}",
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"Content-Type": "application/json"},
        )

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)
