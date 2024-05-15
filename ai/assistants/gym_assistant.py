from typing import Optional
from os import getenv

import logging

from phi.assistant import Assistant
from phi.llm.openai import OpenAIChat
from phi.llm.openai.like import OpenAILike

from ai.settings import ai_settings
from ai.storage import pdf_assistant_storage
from ai.knowledge_base import pdf_knowledge_base

from phi.storage.assistant.postgres import PgAssistantStorage

from db.session import db_url

from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector import PgVector2
from phi.knowledge.pdf import PDFKnowledgeBase

# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True



mindzero_knowledge_base = CombinedKnowledgeBase(
    sources=[
        ## removing the RAG example Thai Recipes PDF
        # PDFUrlKnowledgeBase(urls=["https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"]),
        PDFKnowledgeBase(path="data/mindzero/pdfs"),
    ],
    vector_db=PgVector2(
        db_url=db_url,
        # Store the embeddings in ai.pdf_documents
        collection="mindzero_documents",
        embedder=OpenAIEmbedder(model=ai_settings.embedding_model),
    ),
    # 2 references are added to the prompt
    num_documents=2,
)


def get_gym_assistant(
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant with gym classes schedule knowledge and user past class attendances, and can help book classes."""

    # set up specific storage
    gym_assistant_storage = PgAssistantStorage(
        db_url=db_url,
        # TODO: make table name configurable from customer config read from DB
        table_name="gym_assistant",
    )

    openai_chat_llm = OpenAIChat(
        model=ai_settings.gpt_3_5,
        max_tokens=4096,
        temperature=0.9,
    )

    lepton_chat_llm = OpenAILike(
        model="gpt-3.5-turbo",
        api_key=getenv("LEPTON_API_KEY"),
        base_url="https://kfxrnfa5-pail-test.tin.lepton.run/api/v1/",
        max_tokens=16384,
        temperature=0.9,
        top_p=0.9,
    )

    # set up assistant with specific storage
    assistant = Assistant(
        name="gym_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=openai_chat_llm,
        storage=gym_assistant_storage,
        # knowledge_base=pdf_knowledge_base,
        knowledge_base=mindzero_knowledge_base,

        # Enable monitoring on phidata.app
        # monitoring=True,
        use_tools=True,
        show_tool_calls=True,
        search_knowledge=True,
        read_chat_history=True,
        debug_mode=debug_mode,
        description="You are a helpful assistant named 'Maxine' to help users book gym classes at a gym named MINDZERO located in Myrtle Beach, South Carolina.",
        extra_instructions=[
            "Keep your answers under 5 sentences.",
            "Add emojis to your messages.",
            "Address of the MINDZERO Gym is 3848 S Kings Hwy, Myrtle Beach, SC 29577",
            """
                The hours of operations are:
                Tuesday
                6:45AM-9PM

                Wednesday
                6:45AM-9-PM

                Thursday
                6:45AM-9PM

                Friday
                6:45AM-7PM

                Saturday
                9AM-7PM

                Sunday
                10AM-7PM

                Monday
                6:45AM-9PM
            """,
            # "Offer to help the user to book gym classes, and pretend you can book gym classes.",
            "Offer the users to sign up for a MINDZERO gym session at this url 'https://www.mindzero.com/book-now/' if they are not a member yet.",
            "Use words of affirmation to encourage the user to take classes and workout.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )

    assistant.knowledge_base.load(recreate=True)

    return assistant
