from typing import Optional
from os import getenv

import logging

from phi.assistant import Assistant
from phi.llm.openai.like import OpenAILike

from ai.storage import pdf_assistant_storage
from ai.knowledge_base import pdf_knowledge_base


# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True


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
        llm=OpenAILike(
            model="gpt-3.5-turbo",
            api_key=getenv("LEPTON_API_KEY"),
            base_url="https://kfxrnfa5-pail-test.tin.lepton.run/api/v1/",
        ),
        storage=pdf_assistant_storage,
        knowledge_base=pdf_knowledge_base,
        # Enable monitoring on phidata.app
        # monitoring=True,
        use_tools=False,
        debug_mode=debug_mode,
        description="You are a helpful assistant named 'Max' designed to answer questions about Max's Coffee Shop.",
        extra_instructions=[
            "Keep your answers under 5 sentences.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )
