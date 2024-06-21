from typing import Any, Dict, Generator, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from phi.assistant import Assistant, AssistantRun
from pydantic import BaseModel

from ai.assistants.coffee_assistant import get_coffee_assistant
from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pdf_auto import get_autonomous_pdf_assistant
from ai.assistants.pdf_rag import get_rag_pdf_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from ai.storage import pdf_assistant_storage
from api.routes.endpoints import endpoints
from utils.log import logger

######################################################
## Router for Serving Assistants
######################################################

assistants_router = APIRouter(prefix=endpoints.ASSISTANTS, tags=["Assistants"])
AssistantType = Literal[
    "AUTO_PDF", "RAG_PDF", "GYM_MINDZERO", "PIZZERIA", "CAFE", "GYM"
]


def get_assistant(
    assistant_type: AssistantType,
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """Return the assistant"""

    if assistant_type == "AUTO_PDF":
        return get_autonomous_pdf_assistant(run_id=run_id, user_id=user_id)
    elif assistant_type == "RAG_PDF":
        return get_rag_pdf_assistant(run_id=run_id, user_id=user_id)
    elif assistant_type == "GYM_MINDZERO":
        return get_gym_assistant(user_id=user_id)
    elif assistant_type == "PIZZERIA":
        # TODO: create a generic Demo Assistants with fake data
        return get_pizza_assistant(user_id=user_id)
    elif assistant_type == "CAFE":
        return get_coffee_assistant(user_id=user_id)
    elif assistant_type == "GYM":
        return get_gym_assistant(user_id=user_id)
    else:
        raise HTTPException(status_code=404, detail="Assistant not found")


class LoadKnowledgeBaseRequest(BaseModel):
    assistant: AssistantType = "RAG_PDF"


@assistants_router.post("/load-knowledge-base")
def load_knowledge_base(body: LoadKnowledgeBaseRequest):
    """Loads the knowledge base for an Assistant"""

    assistant = get_assistant(assistant_type=body.assistant)
    if assistant.knowledge_base:
        assistant.knowledge_base.load(recreate=False)
    return {"message": "Knowledge Base Loaded"}


class CreateRunRequest(BaseModel):
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


class CreateRunResponse(BaseModel):
    run_id: str
    user_id: Optional[str] = None
    chat_history: List[Dict[str, Any]]


@assistants_router.post("/create", response_model=CreateRunResponse)
def create_assistant_run(body: CreateRunRequest):
    """Create a new Assistant run and returns the run_id"""

    logger.debug(f"CreateRunRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, user_id=body.user_id
    )

    # create_run() will log the run in the database and return the run_id
    # which is returned to the frontend to retrieve the run later
    run_id: Optional[str] = assistant.create_run()
    if run_id is None:
        raise HTTPException(status_code=500, detail="Failed to create assistant run")
    logger.debug(f"Created Assistant Run: {run_id}")

    return CreateRunResponse(
        run_id=run_id,
        user_id=assistant.user_id,
        chat_history=assistant.memory.get_chat_history(),
    )


def chat_response_streamer(assistant: Assistant, message: str) -> Generator:
    for chunk in assistant.run(message):
        yield chunk


class ChatRequest(BaseModel):
    message: str
    stream: bool = True
    run_id: Optional[str] = None
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


@assistants_router.post("/chat")
def chat(body: ChatRequest):
    """Sends a message to an Assistant and returns the response"""

    logger.debug(f"ChatRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, run_id=body.run_id, user_id=body.user_id
    )

    if body.stream:
        return StreamingResponse(
            chat_response_streamer(assistant, body.message),
            media_type="text/event-stream",
        )
    else:
        return assistant.run(body.message, stream=False)


class ChatHistoryRequest(BaseModel):
    run_id: str
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


@assistants_router.post("/history", response_model=List[Dict[str, Any]])
def get_chat_history(body: ChatHistoryRequest):
    """Return the chat history for an Assistant run"""

    logger.debug(f"ChatHistoryRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, run_id=body.run_id, user_id=body.user_id
    )
    # Load the assistant from the database
    assistant.read_from_storage()

    return assistant.memory.get_chat_history()


class GetAssistantRunRequest(BaseModel):
    run_id: str
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


@assistants_router.post("/get", response_model=Optional[AssistantRun])
def get_assistant_run(body: GetAssistantRunRequest):
    """Returns the Assistant run"""

    logger.debug(f"GetAssistantRunRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, run_id=body.run_id, user_id=body.user_id
    )

    return assistant.read_from_storage()


class GetAllAssistantRunsRequest(BaseModel):
    user_id: str


@assistants_router.post("/get-all", response_model=List[AssistantRun])
def get_assistants(body: GetAllAssistantRunsRequest):
    """Return all Assistant runs for a user"""

    logger.debug(f"GetAllAssistantRunsRequest: {body}")
    return pdf_assistant_storage.get_all_runs(user_id=body.user_id)


class GetAllAssistantRunIdsRequest(BaseModel):
    user_id: str


@assistants_router.post("/get-all-ids", response_model=List[str])
def get_run_ids(body: GetAllAssistantRunIdsRequest):
    """Return all run_ids for a user"""

    logger.debug(f"GetAllAssistantRunIdsRequest: {body}")
    return pdf_assistant_storage.get_all_run_ids(user_id=body.user_id)


class RenameAssistantRunRequest(BaseModel):
    run_id: str
    run_name: str
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


class RenameAssistantRunResponse(BaseModel):
    run_id: str
    run_name: str


@assistants_router.post("/rename", response_model=RenameAssistantRunResponse)
def rename_assistant(body: RenameAssistantRunRequest):
    """Rename an Assistant run"""

    logger.debug(f"RenameAssistantRunRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, run_id=body.run_id, user_id=body.user_id
    )
    assistant.rename_run(body.run_name)

    return RenameAssistantRunResponse(
        run_id=assistant.run_id,
        run_name=assistant.run_name,
    )


class AutoRenameAssistantRunRequest(BaseModel):
    run_id: str
    user_id: Optional[str] = None
    assistant: AssistantType = "RAG_PDF"


class AutoRenameAssistantRunResponse(BaseModel):
    run_id: str
    run_name: str


@assistants_router.post("/autorename", response_model=AutoRenameAssistantRunResponse)
def autorename_assistant(body: AutoRenameAssistantRunRequest):
    """Rename a assistant using the LLM"""

    logger.debug(f"AutoRenameAssistantRunRequest: {body}")
    assistant: Assistant = get_assistant(
        assistant_type=body.assistant, run_id=body.run_id, user_id=body.user_id
    )
    assistant.auto_rename_run()

    return RenameAssistantRunResponse(
        run_id=assistant.run_id,
        run_name=assistant.run_name,
    )


class WebDemoAssistantListRequest(BaseModel):
    user_id: str


class WebDemoAssistantInfo(BaseModel):
    assistant_display_name: str
    run_id: str
    assistant: AssistantType
    friendliness: float
    fun_and_jokes: float
    emojis: float


class WebDemoAssistantListResponse(BaseModel):
    assistants: List[WebDemoAssistantInfo]


@assistants_router.post(
    "/web-demo-assistants", response_model=WebDemoAssistantListResponse
)
def web_demo_assistants(body: WebDemoAssistantListRequest):
    """Return a list of Web Demo Assistant info for a user"""

    logger.debug(f"WebDemoAssistantListRequest: {body}")

    user_id = body.user_id

    pizzeria_assistant = get_assistant(user_id=user_id, assistant_type="PIZZERIA")
    coffee_assistant = get_assistant(user_id=user_id, assistant_type="CAFE")
    gym_assistant = get_assistant(user_id=user_id, assistant_type="GYM")
    autonomous_assistant = get_assistant(user_id=user_id, assistant_type="AUTO_PDF")

    # TODO: change get_autonomous_pdf_assistant to auto-load run id
    auto_assistant_run_id = None
    auto_assistant_run_ids = autonomous_assistant.get_all_run_ids(user_id=user_id)
    auto_assistant_run_id = (
        auto_assistant_run_ids[0] if auto_assistant_run_ids else None
    )

    assistant_list = [
        {
            "assistant_display_name": "Anna",
            "run_id": auto_assistant_run_id,
            "assistant": "AUTO_PDF",
            "friendliness": 1.0,
            "fun_and_jokes": 0.5,
            "emojis": 0.8,
        },
        {
            "assistant_display_name": "Pizzeria",
            "run_id": pizzeria_assistant.run_id,
            "assistant": "PIZZERIA",
            "friendliness": 1.0,
            "fun_and_jokes": 0.8,
            "emojis": 1.0,
        },
        {
            "assistant_display_name": "Cafe",
            "run_id": coffee_assistant.run_id,
            "assistant": "CAFE",
            "friendliness": 1.0,
            "fun_and_jokes": 0.5,
            "emojis": 0.8,
        },
        {
            "assistant_display_name": "Gym",
            "run_id": gym_assistant.run_id,
            "assistant": "GYM",
            "friendliness": 1.0,
            "fun_and_jokes": 0.5,
            "emojis": 0.8,
        },
    ]

    return assistant_list
