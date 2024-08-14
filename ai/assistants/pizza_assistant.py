import json
import logging
import math
from collections import defaultdict

from phi.assistant import Assistant, AssistantMemory
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.json import JSONKnowledgeBase
from phi.knowledge.pdf import PDFKnowledgeBase
from phi.llm.openai import OpenAIChat
from phi.memory.db.postgres import PgMemoryDb
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.tools import Toolkit
from phi.vectordb.pgvector import PgVector2

from ai.settings import ai_settings
from ai.tools.ordering_tools import OrderingTools
from db.session import db_url

# Set up logging
logging.basicConfig(level=logging.ERROR)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.ERROR)
requests_log.propagate = True

# set up specific knowledge base
pizza_knowledge_base = CombinedKnowledgeBase(
    sources=[
        ## removing the RAG example Thai Recipes PDF
        # PDFUrlKnowledgeBase(urls=["https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"]),
        PDFKnowledgeBase(path="data/pizza/pdfs"),
        JSONKnowledgeBase(path="data/pizza/jsons"),
    ],
    vector_db=PgVector2(
        db_url=db_url,
        # Store the embeddings in ai.pdf_documents
        collection="pizza_documents",
        embedder=OpenAIEmbedder(model=ai_settings.embedding_model),
    ),
    # 2 references are added to the prompt
    num_documents=2,
)

# set up specific storage
pizza_assistant_storage = PgAssistantStorage(
    db_url=db_url,
    # TODO: make table name configurable from customer config read from DB
    table_name="pizza_assistant",  # Force using a new table
)


class PizzaMyHeartTools(Toolkit):
    def __init__(self):
        super().__init__(name="pizza_my_heart_tools")
        self.register(self.pizza_calculator)

    def pizza_calculator(
        self,
        num_meat_and_veggie_lovers: str = "0",
        num_vegetarian: str = "0",
        num_vegan: str = "0",
        num_kids: str = "0",
    ) -> str:
        """Use this function to calculate the number of each pizza needed for the user.

        Args:
            num_meat_and_veggie_lovers (str): Number of meat and veggie lovers. Defaults to 0.
            num_vegetarian (str): Number of vegetarians. Defaults to 0.
            num_vegan (str): Number of vegans. Defaults to 0.
            num_kids (str): Number of kids. Defaults to 0.

        Returns:
            str: JSON string of the number of each pizza needed.
        """
        # Number too large
        if (
            len(num_meat_and_veggie_lovers) > 2
            or len(num_vegetarian) > 2
            or len(num_vegan) > 2
            or len(num_kids) > 2
        ):
            return "Input too large, please contact store about request"

        # Negative number
        if (
            num_meat_and_veggie_lovers[0] == "-"
            or num_vegetarian[0] == "-"
            or num_vegan[0] == "-"
            or num_kids[0] == "-"
        ):
            return "Negative input, please contact store about request"

        # Convert all strings
        num_meat_and_veggie_lovers = int(num_meat_and_veggie_lovers)
        num_vegetarian = int(num_vegetarian)
        num_vegan = int(num_vegan)
        num_kids = int(num_kids)

        num_pizza_meat_and_veggie_lovers = math.floor(
            num_meat_and_veggie_lovers * 0.25 + 0.5
        )
        num_pizza_vegetarian = math.floor(num_vegetarian * 0.2 + 0.5)
        num_pizza_vegan = math.floor(num_vegan * 0.2 + 0.5)
        num_pizza_kids = math.floor(num_kids * 0.125 + 0.5)

        pizzas = defaultdict(int)

        BIGSUR = "BigSur"
        COWELLSCOMBO = "CowellsCombo"
        DLEX = "DLex"
        PEPPERONI = "Pepperoni"
        THEHOOK = "TheHook"
        PESTO = "Pesto"
        PRIMA = "Prima"
        CHEESE = "Cheese"
        VEGANBIGSUR = "VeganBigSur"
        MTDIABLO = "MtDiablo"
        MAUIWOWIE = "MauiWowie"

        for i in range(num_pizza_meat_and_veggie_lovers):
            case = i % 4
            if case == 0:
                pizzas[BIGSUR] += 1
            if case == 1:
                pizzas[COWELLSCOMBO] += 1
            if case == 2:
                pizzas[DLEX] += 1
            if case == 3:
                pizzas[PEPPERONI] += 1

        for i in range(num_pizza_vegetarian):
            case = i % 4
            if case == 0:
                pizzas[THEHOOK] += 1
            if case == 1:
                pizzas[PESTO] += 1
            if case == 2:
                pizzas[PRIMA] += 1
            if case == 3:
                pizzas[CHEESE] += 1

        for i in range(num_pizza_vegan):
            case = i % 4
            if case == 0:
                pizzas[VEGANBIGSUR] += 1
            if case == 1:
                pizzas[MTDIABLO] += 1
            if case == 2:
                pizzas[VEGANBIGSUR] += 1
            if case == 3:
                pizzas[MTDIABLO] += 1

        for i in range(num_pizza_kids):
            case = i % 4
            if case == 0:
                pizzas[CHEESE] += 1
            if case == 1:
                pizzas[PEPPERONI] += 1
            if case == 2:
                pizzas[MAUIWOWIE] += 1
            if case == 3:
                pizzas[PEPPERONI] += 1

        return json.dumps(pizzas)


def get_pizza_assistant(
    user_id: str,
    new_run: bool = False,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant for a pizza store with menu knowledge."""

    # Ensure AssistantMemory unique per user
    memory = AssistantMemory(
        db=PgMemoryDb(db_url=db_url, table_name="pizza_memory"),
        user_id=user_id,
    )

    run_id = None
    if not new_run:
        run_ids = pizza_assistant_storage.get_all_run_ids(user_id=user_id)
        run_id = run_ids[0] if run_ids else None

    # Need to address circular dependency:
    # OrderingTools needs Assistant to set assistant field
    # Assistant needs OrderingTools to set tools field.
    ordering_tools = OrderingTools()

    # set up assistant with specific storage
    assistant = Assistant(
        name="pizza_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=OpenAIChat(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0,
            function_call_limit=1000000,
        ),
        # llm=get_llm(LLM.MODAL),
        storage=pizza_assistant_storage,
        add_chat_history_to_messages=True,
        add_chat_history_to_prompt=False,
        num_history_messages=10,
        # knowledge_base=pdf_knowledge_base,
        knowledge_base=pizza_knowledge_base,
        # Add personalization to the assistant by creating memories
        create_memories=False,
        # Update memory after each run
        update_memory_after_run=False,
        # Store the memories in a database
        memory=memory,
        add_references_to_prompt=True,
        # Enable monitoring on phidata.app
        # monitoring=True,
        tools=[
            ordering_tools,
            PizzaMyHeartTools(),
        ],
        use_tools=True,
        show_tool_calls=debug_mode,  # show tool calls in debug mode. Set to True for dev purposes (see function calls)
        search_knowledge=True,
        read_chat_history=True,
        debug_mode=debug_mode,
        build_default_system_prompt=True,
        description="""
Your name is Jimmy. You are a surfer from California. You love surfing and you love pizza. You want to tell everyone about Pizza My Heart pizza.
You answer customer questions about the Pizza My Heart pizzas with passion. You respond in a precise, concise, and oh-so-relatable casual tone. You really care about all of your customers, new and old. You treat your customers like your own family and best friends.
You help customers order at your store. Your role is to help users order from Pizza My Heart if they express interest in ordering. You can add items to the user's order, remove items from the user's order, and place the user's order.
""",
        instructions=[
            "Use emojis at the right time.",
            "Always be polite and pleasant.",
            "Be humorous",
            "Only answer topics about the pizza store.",
            "Include image links of the menu items in your response if you have not sent them in your earlier messages.",
            "Recommend different pizzas. do not repeat the same pizza more than once.",
            "Ask customers about salad and drinks to go with their order occasionally.",
            "When customers complain about the pizza because of order mixup, or delivery delay, offer them another pizza and apologize for their inconvenience.",
            "Search the knowledge base for answers to answer questions about Brand Story, founder's story, awards, menu items, and promotions.",
            "You must use the set_user_first_name tool to save the user's first name every time they mention their first name.",
            "You must use the set_user_last_name tool to save the user's last name every time they mention their last name.",
            "You must use the set_user_email tool to save the user's email every time they mention their email.",
            "You must use the set_user_phone_number tool to save the user's phone number every time they mention their phone number.",
            'You must use the set_order_type tool to save the user\'s desired order type every time they mention their desired order type. The options are "pickup" or "delivery".',
            "You must use the set_delivery_address tool to save the user's delivery address every time they mention their delivery address.",
            "You must use the set_delivery_suite_number tool to save the user's suite number every time they mention their suite number as a part of their delivery address.",
            "You must use the set_delivery_city tool to save the user's city every time they mention their city as a part of their delivery address.",
            "You must use the set_delivery_state tool to save the user's state every time they mention their state as a part of their delivery address.",
            "You must use the set_delivery_zip tool to save the user's zip every time they mention their zip as a part of their delivery address.",
            "You must use the add_to_order tool to add items to the user's order every time the user expresses interest in ordering. For example, if the user says \"I'd like to order\" then use this tool.",
            "You must use the remove_from_order tool to remove items from the user's order every time the user expresses interest in removing from their order.",
            'You must use the place_order tool to place the user\'s order every time the user expresses interest in placing their order. For example, if the user says "I\'m ready to place my order" or "I\'m ready to check out" then use this tool.',
            "You must use the tools available to you to help the user with their order every time they express interest in ordering.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )

    # Temporary solution: Set the fields for the ordering tools
    ordering_tools.set_fields(
        assistant=assistant, user_id=user_id, add_cart_to_system_prompt=True
    )

    # Not sure why it's recreated every time
    # assistant.knowledge_base.load(recreate=True)

    return assistant
