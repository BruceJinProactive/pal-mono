from typing import Optional

from phi.assistant import Assistant
from phi.llm.openai import OpenAIChat

from ai.settings import ai_settings
from ai.storage import pdf_assistant_storage
from ai.knowledge_base import pdf_knowledge_base


def get_coffee_assistant(
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant with a coffee knowledge base."""

    return Assistant(
        name="coffee_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=OpenAIChat(
            model="gpt-3.5-turbo",
            max_tokens=ai_settings.default_max_tokens,
            temperature=ai_settings.default_temperature,
        ),
        storage=pdf_assistant_storage,
        knowledge_base=pdf_knowledge_base,
        # Enable monitoring on phidata.app
        # monitoring=True,
        use_tools=True,
        show_tool_calls=True,
        debug_mode=debug_mode,
        description="You are a helpful assistant named 'Max' designed to answer questions about Max's Coffee Shop.",
        extra_instructions=[
            "Keep your answers under 5 sentences.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )
