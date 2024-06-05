import json
import logging
import math
from collections import defaultdict
from typing import Optional

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
from db.session import db_url

# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
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


memory = AssistantMemory(
    db=PgMemoryDb(
        db_url=db_url,
        table_name="pizza_memory",
    ),
)


class PizzaTools(Toolkit):
    def __init__(self):
        super().__init__(name="pizza_tools")
        self.register(self.get_pizzas)

    def get_pizzas(
        self,
        num_meat_and_veggie_lovers: str = None,
        num_vegetarian: str = None,
        num_vegan: str = None,
        num_kids: str = "0",
        num_adults: str = "0",
    ) -> str:
        """Use this function to calculate the number of each pizza needed. This is the pizza calculator.
            If the user hasn't supplied info, ask for number of adults and kids then use this function.
            If the number of adults is known but not number of vegetarians or vegans, ask for the number of adult vegetarians and vegans then use this function with the num_kids and num_adults.

        Args:
            num_meat_and_veggie_lovers (str): Number of meat and veggie lovers. Default 0.
            num_vegetarian (str): Number of vegetarians. Default 0.
            num_vegan (str): Number of vegans. Default 0.
            num_kids (str): Number of kids. Default to 0 if none supplied.
            num_adults (str): Number of adults. Default to 0 if none supplied.

        Returns:
            str: JSON string of the number of each pizza needed.
                    Returns "Get number of adults and kids" if the user needs to supply the number of adults and kids.
                    Returns "Get number of vegetarians and vegans" if the user needs to supply the number of adult vegetarians and vegans.
        """
        # Number too large
        if (
            num_meat_and_veggie_lovers
            and len(num_meat_and_veggie_lovers) > 2
            or num_vegetarian
            and len(num_vegetarian) > 2
            or num_vegan
            and len(num_vegan) > 2
            or len(num_kids) > 2
            or len(num_adults) > 3
        ):
            return "Contact Store about request"

        # Negative number
        if (
            num_meat_and_veggie_lovers
            and num_meat_and_veggie_lovers[0] == "-"
            or num_vegetarian
            and num_vegetarian[0] == "-"
            or num_vegan
            and num_vegan[0] == "-"
            or num_kids[0] == "-"
            or num_adults[0] == "-"
        ):
            return "Contact Store about request"

        # No inputs
        if (
            not num_meat_and_veggie_lovers
            and not num_vegetarian
            and not num_vegan
            and num_kids == "0"
            and num_adults == "0"
        ):
            return "Get number of adults and kids"

        # Ask for number of vegans and vegetarians if the number of adults is supplied.
        if num_adults != "0" and not num_vegan and not num_vegetarian:
            return "Get number of vegetarians and vegans"

        # Convert all strings
        num_meat_and_veggie_lovers = (
            int(num_meat_and_veggie_lovers) if num_meat_and_veggie_lovers else 0
        )
        num_vegetarian = int(num_vegetarian) if num_vegetarian else 0
        num_vegan = int(num_vegan) if num_vegan else 0
        num_kids = int(num_kids)
        num_adults = int(num_adults)

        # Deduce number of meat and veggie lovers if it hasn't been supplied.
        if not num_meat_and_veggie_lovers and num_adults:
            num_meat_and_veggie_lovers = num_adults - num_vegan - num_vegetarian

        # In case number of vegans and vegetarians is somehow higher than the number of meat and veggie lovers.
        if num_meat_and_veggie_lovers < 0:
            return "Contact Store about request"

        num_meat_and_veggie_lovers = math.floor(num_meat_and_veggie_lovers * 0.25 + 0.5)
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

        for i in range(num_meat_and_veggie_lovers):
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
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant for a pizza store with menu knowledge."""

    # set up assistant with specific storage
    assistant = Assistant(
        name="pizza_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=OpenAIChat(
            model=ai_settings.gpt_3_5,
            max_tokens=4096,
            temperature=0.9,
        ),
        # llm=get_llm(LLM.MODAL),
        storage=pizza_assistant_storage,
        add_chat_history_to_messages=True,
        num_history_messages=1,
        # knowledge_base=pdf_knowledge_base,
        knowledge_base=pizza_knowledge_base,
        # Add personalization to the assistant by creating memories
        create_memories=True,
        # Update memory after each run
        update_memory_after_run=True,
        # Store the memories in a database
        memory=memory,
        add_references_to_prompt=True,
        # Enable monitoring on phidata.app
        # monitoring=True,
        tools=[PizzaTools()],
        use_tools=True,
        show_tool_calls=debug_mode,  # show tool calls in debug mode
        search_knowledge=True,
        read_chat_history=False,
        debug_mode=debug_mode,
        build_default_system_prompt=False,
        system_prompt="""
Your name is Jimmy. You are a  surfer from California. You love surfing and your love pizza. You want to tell everyone about Pizza My Heart pizza.
You answer customer questions about the Pizza My Heart pizzas with passion. You respond in a precise, concise, and oh-so-relatable casual tone. You really care about all of your customers, new and old. You treat her customers like you own family and best friends.

Here are the instructions you must follow:
<instructions>
1. Only answer topics about the pizza store.
2. Always tell customer your name first and then always ask for their names. 
3. Always address customers by their name in this conversation if you know their name. If you don't know their name, ask what their names are.
4. Use the pizza calculator tool to calculate the number of pizzas needed for any question related to planning orders. Use the chat history to determine arguments. 
5. Use emojis at the right time.
6. Always be polite and pleasant.
7. Be humorous 
8. Recommend different pizzas. do not repeat the same pizza more than once.
9. Ask customers about salad and drinks to go with their pizza
10. When customers complain about the pizza because of order mixup, or delivery delay, offer them another pizza and apologize for their inconvenience.
11. Search the knowledge base for answers to answer questions about Brand Story, founder's story, awards, menu items, and promotions.
</instructions>
""",
        assistant_data={"assistant_type": "autonomous"},
    )

    # Not sure why it's recreated every time
    # assistant.knowledge_base.load(recreate=True)

    return assistant
