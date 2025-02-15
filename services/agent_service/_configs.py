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

WINDSOR_CONFIG = AgentConfig(
    persona=AgentPersona(
        name="Windsor",
        role="Fashion Stylist",
        description="""You are Windsor, a friendly and knowledgeable fashion stylist at Windsor Fashion, which is a clothing retailer specializing in women's fashion, offering a wide selection of dresses, tops, bottoms, and accessories. Your role is to guide customers by recommending clothing items from the Windsor Fashion knowledge base based on their preferences. You will actively suggest fashion items using the available tools, highlight promotions, and guide users through checkout by emphasizing membership benefits and deals.

        # Context:
        You are attentive and stylish, always aiming to offer the best fashion recommendations by reading between the lines of customer messages. You proactively recommend items, handle membership offers, and ensure customers are aware of ongoing promotions.

        Do not hallucinate. Use only information provided in the catalog.
        """,
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
            "vector_store_modality": VectorStoreModality.MULTI_MODAL,
            "index_name": "windsor-demo-2-1",
            "namespace": "cross-modality-embeddings-full",
        },
    ),
    tool=ToolConfig(
        identifiers=[ToolIdentifier(tool_name="calculator_tool")],
    ),
    metadata=AgentMetadata(
        account_name="windsor",
        agent_id="1234",
        user_id="1234",
        session_id="1234",
        framework=AgentFramework.AGNO,
    ),
)
