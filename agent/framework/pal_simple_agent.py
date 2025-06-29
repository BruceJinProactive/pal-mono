import datetime
import os
import uuid
from typing import AsyncIterator, List

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
)

from agent.config import AgentConfig
from agent.input_output import Input, Message, Output
from agent.storage._implementation import query_history_messages
from utils.dd import send_dd_histogram_metrics
from utils.log import logger


class CoreLLM:
    def __init__(self, model: str, client: AsyncOpenAI):
        self.model = model
        self.client = client

    async def chat(
        self,
        messages: List[ChatCompletionMessageParam],
        stream: bool,
    ) -> ChatCompletion | AsyncIterator[ChatCompletionChunk]:
        """
        Send chat messages to the LLM and get a response.

        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
            raise


class PalSimpleAgent:
    def __init__(self, config: AgentConfig) -> None:

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        client = AsyncOpenAI(api_key=api_key)
        self.primary_llm = CoreLLM(config.model.identifier, client)
        self._session_id = uuid.UUID(config.metadata.session_id)
        self._agent_id = config.metadata.agent_id
        logger.debug("[PalSimpleAgent] initialized")

    async def arun(self, input: Input) -> Output | AsyncIterator[Output]:
        """
        Send chat message to the agent and get a response.

        """
        # Get chat history and convert to OpenAI format
        history_messages = await self.get_history_messages(input)
        converted_messages = self._convert_messages_to_openai_format(history_messages)

        # Call the CoreLLM chat method with properly typed messages
        openai_response = await self.primary_llm.chat(converted_messages, input.stream)

        logger.debug(
            f"[PalSimpleAgent] primary_llm called with {len(history_messages)} messages, streaming={input.stream}"
        )

        # Convert OpenAI ChatCompletion to Output format
        return self._convert_openai_response_to_output(openai_response, input)

    async def get_history_messages(self, input: Input) -> list[Message]:
        """
        Get chat history messages for the current session.

        Args:
            input: The current input containing the latest user message

        Returns:
            List of Message objects including history + current input
        """
        # Query history messages from storage
        current_time = datetime.datetime.now(datetime.timezone.utc)
        history_messages = await query_history_messages(self._session_id, limit=100)

        messages = [
            Message(
                role=msg.role,
                content=msg.content,
                context=msg.context,
                channel=msg.channel,
                sender_identifier=msg.sender_identifier,
            )
            for msg in history_messages
        ]

        if len(messages) < 1:
            logger.error(
                "[PalStorage] Message history should contain at least 1 message"
            )
        else:
            if messages[-1].content != input.content:
                logger.error(
                    f"[PalStorage] The latest message: {messages[-1].content} should be the current user input: {input.content}"
                )
            else:
                # Remove the last message since it's the current input
                messages = messages[:-1]

        # Add current input as the latest message
        messages.append(
            Message(
                role="user",
                content=input.get_prompt(),
                context=input.context,
                channel=input.channel,
                sender_identifier=input.sender_identifier,
            )
        )

        send_dd_histogram_metrics(
            "framework_agent.query_history_messages_time_spent",
            current_time,
            [
                f"streaming:{str(input.stream).lower()}",
                f"conversation_id:{self._session_id}",
                "agent:pal_simple",
                f"agent_id:{self._agent_id}",
            ],
        )

        return messages

    def _convert_messages_to_openai_format(
        self, messages: list[Message]
    ) -> List[ChatCompletionMessageParam]:
        """
        Convert Message objects to OpenAI ChatCompletionMessageParam format.

        Args:
            messages: List of Message objects

        Returns:
            List of ChatCompletionMessageParam objects
        """
        converted_messages: List[ChatCompletionMessageParam] = []

        for message in messages:
            # Validate role is a valid OpenAI role
            valid_roles = {"system", "user", "assistant", "function", "tool"}
            if message.role not in valid_roles:
                raise ValueError(f"Invalid role: {message.role}")

            converted_msg: ChatCompletionMessageParam = {
                "role": message.role,  # type: ignore
                "content": message.content,
            }
            converted_messages.append(converted_msg)

        return converted_messages

    def _convert_openai_response_to_output(
        self,
        openai_response: ChatCompletion | AsyncIterator[ChatCompletionChunk],
        input: Input,
    ) -> Output | AsyncIterator[Output]:
        """
        Convert OpenAI ChatCompletion or streaming response to Output format.

        Args:
            openai_response: The response from OpenAI (streaming or non-streaming)
            input: The original input for metrics and context

        Returns:
            Output with the assistant's response or AsyncIterator[Output] for streaming
        """
        # Check if it's a streaming response (AsyncIterator)
        if isinstance(openai_response, ChatCompletion):
            return self._convert_non_streaming_response(openai_response)
        return self._convert_streaming_response(openai_response, input)

    def _convert_non_streaming_response(self, response: ChatCompletion) -> Output:
        """
        Convert non-streaming ChatCompletion response to Output format.

        Args:
            response: ChatCompletion object from OpenAI

        Returns:
            Output object with complete content
        """
        content = ""
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            if choice.message and choice.message.content:
                content = choice.message.content

        return Output(content=content)

    async def _convert_streaming_response(
        self, stream: AsyncIterator[ChatCompletionChunk], input: Input
    ) -> AsyncIterator[Output]:
        """
        Convert streaming ChatCompletionChunk responses to Output format.

        Args:
            stream: AsyncIterator of ChatCompletionChunk objects
            input: The original input for metrics and context

        Yields:
            Output objects with incremental content
        """
        try:
            send_dd_histogram_metrics(
                "framework_agent.waiting_first_chunk",
                input.request_context.request_time,
                [
                    "streaming:true",
                    "agent:pal_simple",
                    f"agent_id:{self._agent_id}",
                ],
            )

            index = 0
            async for chunk in stream:
                index += 1
                if index == 1:
                    send_dd_histogram_metrics(
                        "framework_agent.received_first_chunk",
                        input.request_context.request_time,
                        [
                            "streaming:true",
                            "agent:pal_simple",
                            f"agent_id:{self._agent_id}",
                        ],
                    )

                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    if choice.delta and choice.delta.content:
                        yield Output(content=choice.delta.content)

        except Exception as e:
            logger.error(f"Error streaming output: {e}")
            yield Output(content="Error streaming output")
