from enum import Enum
from os import getenv

from phi.llm.openai import OpenAIChat
from phi.llm.openai.like import OpenAILike

from ai.settings import ai_settings


class LLM(Enum):
    OPENAI = "OPENAI"
    LEPTON = "LEPTON"
    MODAL = "MODAL"


def get_llm(llm_name: LLM):
    if llm_name == LLM.OPENAI:
        return OpenAIChat(
            model=ai_settings.gpt_3_5,
            max_tokens=4096,
            temperature=0.9,
        )
    elif llm_name == LLM.LEPTON:
        return OpenAILike(
            model="gpt-3.5-turbo",
            api_key=getenv("LEPTON_API_KEY"),
            base_url="https://kfxrnfa5-pail-test.tin.lepton.run/api/v1/",
            max_tokens=16384,
            temperature=0.9,
            top_p=0.9,
        )
    elif llm_name == LLM.MODAL:
        return OpenAILike(
            model="OpenHermes-2.5-Mistral-7B-dpo",
            api_key=getenv("MODAL_API_KEY"),
            base_url="https://proactive-ai-lab--openai-b-fastapi-app.modal.run/",
            max_tokens=16384,
            temperature=0.9,
            top_p=0.9,
        )
    else:
        raise ValueError(f"Invalid model name: {llm_name}")
