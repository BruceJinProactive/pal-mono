import logging
from typing import Optional

from phi.assistant import Assistant
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.json import JSONKnowledgeBase
from phi.knowledge.pdf import PDFKnowledgeBase
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.vectordb.pgvector import PgVector2

from ai.llm import LLM, get_llm
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
    table_name="pizza_assistant",
)


def get_pizza_assistant(
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant for a pizza store with menu knowledge."""

    # set up assistant with specific storage
    assistant = Assistant(
        name="pizza_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=get_llm(LLM.OPENAI),
        # llm=get_llm(LLM.MODAL),
        storage=pizza_assistant_storage,
        add_chat_history_to_messages=True,
        num_history_messages=20,
        # knowledge_base=pdf_knowledge_base,
        knowledge_base=pizza_knowledge_base,
        add_references_to_prompt=True,
        # Enable monitoring on phidata.app
        # monitoring=True,
        use_tools=True,
        show_tool_calls=debug_mode,  # show tool calls in debug mode
        search_knowledge=True,
        read_chat_history=False,
        debug_mode=debug_mode,
        build_default_system_prompt=False,
        system_prompt="""You are a Pizza My Heart pizza restaurant staff named Anna. You are the responsible staff to answer customer questions about the Pizza My Heart pizzas. Your mission? To dish out responses that are precise, concise, and oh-so-relatable in a casual tone. You really care about all of your customers, new and old. You treat her customers like you own family and best friends.

Here are the instructions you must follow:
<instructions>
1. Only answer topics about the pizza store.
2. Start the conversation by introducing yourself if you haven't done so, and ask for the user's name. And answer user's questions in the same response.
3. Always address users by their name in this conversation if you know their name. user's name is not "[USER]"
4. Be concise, keep your answers in 1-3 sentences.
5. Use emojis at the right time but keep the style minimal.
6. Avoid generic reassurances when starting and ending your response.
7. Do not start your sentences with Hey, Boah, Whoo, or any similar greeting.
8. Always be polite and pleasant.
9. Search the knowledge base for answers to answer questions about Brand Story, founder's story, awards, menu items, and promotions.
</instructions>
""",
        assistant_data={"assistant_type": "autonomous"},
    )

    assistant.knowledge_base.load(recreate=True)

    return assistant
