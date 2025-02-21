import uuid

from agent import (
    AgentConfig,
    AgentFramework,
    AgentMetadata,
    AgentPersona,
    KnowledgeConfig,
    KnowledgeProvider,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
    ToolIdentifier,
    VectorStoreModality,
    VectorStoreProvider,
)

# Sample agent config
ANNA_CONFIG = AgentConfig(
    persona=AgentPersona(
        name="Anna",
        role="Coffee Barista",
        description="""You are Anna, a 24 year old from Southern California. You went to college in SoCal and are now studying for the LSAT to go to law school next year.

        Do not hallucinate. Use only information provided on the menu.
        """,
    ),
    model=ModelConfig(
        identifier="medium",
        stream=False,
    ),
    memory=MemoryConfig(
        enabled=True,
        identifier="palona",
        instruction="Don't remember user's gender",
    ),
    knowledge=KnowledgeConfig(
        enabled=True,
        provider=KnowledgeProvider.LLAMAINDEX,
        identifier="palona",
        settings={
            "vector_store_provider": VectorStoreProvider.PINECONE,
            "vector_store_modality": VectorStoreModality.MULTI_MODAL,
            "index_name": "agents",
            "namespace": "default",
        },
    ),
    tool=ToolConfig(
        identifiers=[ToolIdentifier(tool_name="calculator_tool")],
    ),
    metadata=AgentMetadata(
        account_name="palona",
        agent_id="123",
        user_id="123",
        session_id="123",
        framework=AgentFramework.AGNO,
    ),
)

windsor_user_id = str(uuid.uuid4())
windsor_session_id = str(uuid.uuid4())
windsor_agent_id = "1234"

WINDSOR_CONFIG = AgentConfig(
    persona=AgentPersona(
        name="Windsor",
        role="Fashion Stylist",
        description="""PLACEHOLDER DESCRIPTION. We will input the windsor agent through the UI.""",
    ),
    model=ModelConfig(
        identifier="medium",
        stream=False,
    ),
    memory=MemoryConfig(
        enabled=True,
        identifier="windsor",
        instruction="Don't remember user's gender",
    ),
    knowledge=KnowledgeConfig(
        enabled=True,
        provider=KnowledgeProvider.LLAMAINDEX,
        identifier="windsor",
        settings={
            "vector_store_provider": VectorStoreProvider.PINECONE,
            "vector_store_modality": VectorStoreModality.TEXT,
            "index_name": "windsor-demo-2-1",
            "namespace": "cross-modality-embeddings-full",
        },
    ),
    tool=ToolConfig(
        identifiers=[
            ToolIdentifier(
                tool_name="windsor_tool",
                args={
                    "session_id": windsor_session_id,
                    "user_id": windsor_user_id,
                    "agent_id": windsor_agent_id,
                },
            )
        ],
    ),
    metadata=AgentMetadata(
        account_name="windsor",
        agent_id=windsor_agent_id,
        user_id=windsor_user_id,
        session_id=windsor_session_id,
        framework=AgentFramework.AGNO,
    ),
)
