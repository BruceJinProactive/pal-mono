# import os
# from typing import AsyncIterator

from agno.models.openai import OpenAIChat

from .schema import ModelOptions

# from portkey_ai import AsyncPortkey
# from portkey_ai.api_resources.apis.create_headers import createHeaders
# from portkey_ai.api_resources.global_constants import PORTKEY_BASE_URL
# from portkey_ai.api_resources.types.chat_complete_type import (
#     ChatCompletionChunk,
#     ChatCompletions,
# )

# from utils.log import logger


# def _build_portkey_client(model_option: ModelOptions) -> AsyncPortkey:
#     portkey_config_id = os.getenv(model_option.env_key)
#     if not portkey_config_id:
#         raise ValueError("Portkey configuration not found.")
#     portkey_api_key = os.getenv("PORTKEY_API_KEY")
#     if not portkey_api_key:
#         raise ValueError("Portkey API key not found.")
#     return AsyncPortkey(api_key=portkey_api_key, config=portkey_config_id)
#
#
# async def call_llm_default(model_option: ModelOptions, params: dict) -> ChatCompletions:
#     portkey = _build_portkey_client(model_option)
#
#     try:
#         response = await portkey.chat.completions.create(stream=False, **params)
#         if not isinstance(response, ChatCompletions):
#             raise TypeError("Unexpected return type from Portkey.")
#         return response
#     except Exception as e:
#         logger.exception(f"Chat completion call to Portkey failed: {str(e)}")
#         raise e
#
#
# async def call_llm_stream(
#     model_option: ModelOptions, params: dict
# ) -> AsyncIterator[ChatCompletionChunk]:
#     portkey = _build_portkey_client(model_option)
#
#     try:
#         response = await portkey.chat.completions.create(stream=True, **params)
#         if not isinstance(response, AsyncIterator):
#             raise TypeError("Unexpected return type from Portkey.")
#         return response
#     except Exception as e:
#         logger.exception(f"Chat completion call to Portkey failed: {str(e)}")
#         raise e


def build_agno_model(model_option: ModelOptions) -> OpenAIChat:

    return OpenAIChat(id="gpt-4o")
    # portkey_config_id = os.getenv(model_option.env_key)
    # if not portkey_config_id:
    #     raise ValueError("Portkey configuration not found.")
    # portkey_api_key = os.getenv("PORTKEY_API_KEY")
    # if not portkey_api_key:
    #     raise ValueError("Portkey API key not found.")
    # return OpenAILike(
    #     id=model_option.model_name,
    #     api_key="placeholder",  # Required, real API key in header
    #     base_url=PORTKEY_BASE_URL,
    #     default_headers=createHeaders(
    #         api_key=portkey_api_key, config=portkey_config_id
    #     ),
    # )
