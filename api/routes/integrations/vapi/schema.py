from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

# ============================================================================
# DATA CLASSES
# ============================================================================


class CallerInfo(BaseModel):
    """Structured caller information."""

    sender_identifier: str
    recipient_identifier: str
    call_id: str


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class VAPIAssistant(BaseModel):
    """VAPI Assistant configuration model."""

    name: str
    firstMessage: Optional[str] = None
    transcriber: Dict[str, Any]
    voice: Dict[str, Any]
    backgroundSound: str
    silenceTimeoutSeconds: int = 60
    backgroundDenoisingEnabled: bool = True
    model: Dict[str, Any] | str | None = None

    model_config = ConfigDict(extra="allow")


class AssistantDestination(BaseModel):
    """Configuration for assistant transfer destinations."""

    assistantName: str
    message: str = ""  # Spoken to customer before connecting
    description: str  # Used by AI to choose when/how to transfer
    transferMode: Literal["rolling-history", "swap-system-message-in-history"]
    type: Literal["assistant"] = "assistant"


class SquadMember(BaseModel):
    """Squad member configuration."""

    assistantId: Optional[str] = None
    assistant: Optional[VAPIAssistant] = None
    assistantDestinations: Optional[List[AssistantDestination]] = None

    @model_validator(mode="after")
    def validate_assistant_or_assistant_id(self):
        if self.assistant is None and self.assistantId is None:
            raise ValueError("Either assistant or assistantId must be provided")
        return self


class SquadConfig(BaseModel):
    """Complete squad configuration."""

    name: str
    members: List[SquadMember]
