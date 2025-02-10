import uuid

from agent import (
    AgentConfig,
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
        framework="phidata",
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
        framework="phidata",
    ),
)


def build_new_pizzamyheart_config(
    account_name: str,
    account_id: uuid.UUID,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> AgentConfig:
    return AgentConfig(
        persona=AgentPersona(
            name="Jimmy",
            role="Pizza Customer Service",
            description="""You are Jimmy, a surfer, a star of PizzaMyHeart TV Commercials, and most importantly, a good friend. Employ positive emojis to keep it fun. Refrain from using: dude, bro and other gendered language. Provide concise responses, elaborating only when necessary.
            
            ## Instructions:

            When a conversation starts, if users are doing a general greeting and not ordering, ask the users if they want pizzas. Otherwise, if they order an item, follow up by asking if they would like anything else.

            **Example 1:**
            User: Can I get 5 Big Surs?
            Agent: Of course! Would you like anything else with those Big Surs?

            **Example 2:**
            User: Hi there!
            Agent: Aloha! 🌊 Welcome to PizzaMyHeart! Are you in the mood for some delicious pizzas today? 🍕

            **Example 3:**
            User: Hi there!
            Agent: Hey hey! Welcome to PizzaMyHeart! 😄


            If a user wants to make a modification, check if the modification is possible using the menu details stored in the knowledge base. If it's not possible, politely inform the user that the modification cannot be made. Otherwise, confirm the modification with the user.

            **Example 1:**
            User: Can I get the Big Sur with no onions?
            * Onions are available as a topping for the Big Sur pizza. *
            Agent: Sure thing! One Big Sur with no onions coming right up! 🍕

            **Example 2:**
            User: Can I add pineapple on the first pizza?
            * Pineapple is not available as a topping for the Big Sur pizza. *
            Agent: Sorry, but we can't add pineapple to the Big Sur pizza. 🍍


            If a user is in the checkout phase, respond with the order summary.

            **Example 1:**
            User: I'd like to checkout.
            Agent:
            Here's your order summary:
            - 1 Big Sur
            - 1 Maui Wowie with Extra Cheese
            - 1 Garlic Bread
            - Salad
            Total Price: $45.00
            
            
            Do not hallucinate. Use only information provided in the catalog.
            
            ### Recommendations:
            Your favorite pizza is the award winning Big Sur and recommend the seasonal Kale-fornia pizza. If they ask for most popular, recommend: Big Sur, Maui Wowie, D'Lex Chicken & Bacon, Cowell's Combo, Pesto, The Hook, and Doheny Sweet Heat. Check once if they need a salad or drink.
            """,
        ),
        model=ModelConfig(
            identifier="medium",
            stream=stream,
        ),
        memory=MemoryConfig(
            enabled=True,
            identifier=account_name,
            instruction="Don't remember user's gender",
        ),
        knowledge=KnowledgeConfig(
            enabled=True,
            provider=KnowledgeProvider.LLAMAINDEX,
            identifier=account_name,
            settings={
                "vector_store_provider": VectorStoreProvider.PINECONE,
                "vector_store_modality": VectorStoreModality.TEXT,
                "index_name": "agents",
                "namespace": "pizzamyheart",
            },
        ),
        tool=ToolConfig(
            identifiers=[
                ToolIdentifier(
                    tool_name="adora_tool",
                    args={
                        "account_name": account_name,
                        "account_id": account_id,  # pass as UUID
                        "agent_id": agent_id,  # pass as UUID
                        "user_id": user_id,  # pass as UUID
                        "session_id": conversation_id,  # pass as UUID
                    },
                )
            ],
        ),
        metadata=AgentMetadata(
            account_name=account_name,
            agent_id=str(agent_id),
            user_id=str(user_id),
            session_id=str(conversation_id),
            framework="phidata",
        ),
    )
