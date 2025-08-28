import datetime
import random
import time
import uuid
from enum import StrEnum
from typing import AsyncIterator, Optional

import agno.agent.agent
from agno.models.message import Message
from agno.run.response import RunResponseContentEvent, ToolCallStartedEvent
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent
from lingua import Language, LanguageDetectorBuilder
from pydantic import BaseModel, Field

from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.memory._implementation import get_all_memories
from agent.model import ModelOptions, build_agno_model
from agent.storage._implementation import query_history_messages
from agent.tool import get_tools
from utils.dd import send_dd_histogram_metrics, trace_block
from utils.log import logger


class FillerType(StrEnum):
    CHAT = "chat"
    TOOL_CALLING = "tool_calling"


class FillerWordsManager:
    """Manages language detection and filler words for chat and tool calling scenarios"""

    # Supported Language enums for language detection and filler words
    _SUPPORTED_LANGUAGES = {
        Language.ENGLISH,
        Language.SPANISH,
        Language.FRENCH,
        Language.ITALIAN,
        Language.CHINESE,
        Language.JAPANESE,
        Language.KOREAN,
    }

    def __init__(
        self,
        chat_filler_words: dict[str, list[str]],
        tool_calling_filler_words: dict[str, list[str]],
        agent_id: str,
        account_name: str,
        chat_filler_words_percentage: int = 100,
        tool_calling_filler_words_percentage: int = 100,
    ):
        self.chat_filler_words = chat_filler_words
        self.tool_calling_filler_words = tool_calling_filler_words
        self.agent_id = agent_id
        self.account_name = account_name
        self.chat_filler_words_percentage = chat_filler_words_percentage
        self.tool_calling_filler_words_percentage = tool_calling_filler_words_percentage
        self._language_detector = self._build_language_detector()

    def _build_language_detector(self):
        """
        Build a language detector with supported languages.

        Returns:
            LanguageDetector: Configured language detector
        """
        return LanguageDetectorBuilder.from_languages(
            *self._SUPPORTED_LANGUAGES
        ).build()

    def detect_input_languages(self, input_content: str) -> list[Language]:
        """
        Detect the language(s) of the input text.

        Args:
            input_content: The text content to analyze

        Returns:
            List of detected languages
        """
        if not input_content or not input_content.strip():
            logger.debug(
                "[FillerWordsManager] Empty input content, skipping language detection"
            )
            return []

        try:
            detected_languages = self._language_detector.detect_multiple_languages_of(
                input_content
            )
            return [
                detected_language.language for detected_language in detected_languages
            ]
        except Exception as e:
            logger.error(f"[FillerWordsManager] Language detection failed: {e}")
            return []

    def get_filler_words(self, language: str, filler_type: FillerType) -> str:
        """
        Generate a filler phrase from configured options for a specific language and type.

        Args:
            language: The language code/name for which to get filler words
            filler_type: Type of filler words (FillerType enum)

        Returns:
            A filler string with flush directive, or empty string if no fillers configured
        """
        # Validate that the language is supported
        supported_language_names = {lang.name for lang in self._SUPPORTED_LANGUAGES}
        if language not in supported_language_names:
            logger.warning(
                f"[FillerWordsManager] Unsupported language '{language}' for {filler_type} filler words. "
                f"Supported languages: {sorted(supported_language_names)}",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                    "language": language,
                    "filler_type": filler_type.value,
                    "supported_languages": sorted(supported_language_names),
                },
            )
            return ""

        # Get the appropriate filler words dictionary based on type
        if filler_type == FillerType.CHAT:
            filler_words_dict = self.chat_filler_words
        elif filler_type == FillerType.TOOL_CALLING:
            filler_words_dict = self.tool_calling_filler_words
        else:
            logger.error(f"[FillerWordsManager] Unknown filler type: {filler_type}")
            return ""

        if not filler_words_dict:
            logger.debug(
                f"[FillerWordsManager] No {filler_type} filler words configured"
            )
            return ""

        # Get filler words for the specific language
        language_filler_words = filler_words_dict.get(language, [])
        if not language_filler_words:
            logger.debug(
                f"[FillerWordsManager] No {filler_type} filler words configured for language: {language}"
            )
            return ""

        # Select a random filler from the configured options for this language
        selected_filler = random.choice(language_filler_words)
        logger.debug(
            f"[FillerWordsManager] Selected {filler_type} filler for {language}: '{selected_filler}'"
        )

        # Empty string in config to control the probability
        if not selected_filler:
            return ""
        return selected_filler + " <flush />"

    def is_language_supported(self, language: str) -> bool:
        """Check if a language is supported for filler words"""
        supported_language_names = {lang.name for lang in self._SUPPORTED_LANGUAGES}
        return language in supported_language_names

    @classmethod
    def get_supported_languages(cls) -> set[Language]:
        """Get the set of supported Language enums"""
        return cls._SUPPORTED_LANGUAGES.copy()

    def get_chat_filler_for_input(self, input_content: str) -> str:
        """
        Get chat filler words with automatic language detection and decision logic.

        Args:
            input_content: The input text to analyze

        Returns:
            Filler words string or empty string if should be skipped
        """
        if not self.chat_filler_words:
            logger.debug(
                "[FillerWordsManager] No chat filler words configured",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                },
            )
            return ""

        if random.randint(1, 100) > self.chat_filler_words_percentage:
            logger.debug(
                f"[FillerWordsManager] Skipping chat filler words due to percentage ({self.chat_filler_words_percentage}%)",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                },
            )
            return ""

        detected_languages = self.detect_input_languages(input_content)

        # Only proceed with filler words if exactly one language is detected
        if len(detected_languages) == 1:
            detected_language = detected_languages[0]
            filler_words = self.get_filler_words(
                detected_language.name, FillerType.CHAT
            )

            if filler_words:
                logger.debug(
                    f"[FillerWordsManager] Chat filler outputted: {filler_words}",
                    extra={
                        "agent_id": self.agent_id,
                        "account_name": self.account_name,
                        "detected_language": detected_language.name,
                    },
                )
            return filler_words
        else:
            logger.debug(
                "[FillerWordsManager] Skipping chat filler words due to multilingual input or detection failure",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                    "detected_languages": [lang.name for lang in detected_languages],
                },
            )
            return ""

    def get_tool_calling_filler_for_input(
        self, input_content: str, tool_name: str = "unknown"
    ) -> str:
        """
        Get tool calling filler words with automatic language detection and decision logic.

        Args:
            input_content: The input text to analyze
            tool_name: Name of the tool being called (for logging)

        Returns:
            Filler words string or empty string if should be skipped
        """
        if not self.tool_calling_filler_words:
            logger.debug(
                "[FillerWordsManager] No tool calling filler words configured",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                },
            )
            return ""

        if random.randint(1, 100) > self.tool_calling_filler_words_percentage:
            logger.debug(
                f"[FillerWordsManager] Skipping tool calling filler words due to percentage ({self.tool_calling_filler_words_percentage}%)",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                },
            )
            return ""

        # Detect languages
        detected_languages = self.detect_input_languages(input_content)

        # Only proceed with filler words if exactly one language is detected
        if len(detected_languages) == 1:
            detected_language = detected_languages[0]
            filler_words = self.get_filler_words(
                detected_language.name, FillerType.TOOL_CALLING
            )

            if filler_words:
                logger.debug(
                    f"[FillerWordsManager] Tool calling filler outputted: {filler_words}",
                    extra={
                        "agent_id": self.agent_id,
                        "account_name": self.account_name,
                        "detected_language": detected_language.name,
                        "tool_name": tool_name,
                    },
                )
            return filler_words
        else:
            logger.debug(
                "[FillerWordsManager] Skipping tool calling filler words due to multilingual input or detection failure",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                    "detected_languages": [lang.name for lang in detected_languages],
                    "tool_name": tool_name,
                },
            )
            return ""


class ResponseModel(BaseModel):
    """Used as structured output response by agent."""

    content: str
    escalated: bool = Field(
        description="Whether the current message should be escalated to a human user.",
        default=False,
    )
    closing_conversation: bool = Field(
        description="Whether or not a conversation should be closed.", default=False
    )


class AgnoAgent:
    def __init__(self, config: AgentConfig):

        tools = [
            tool
            for tool in get_tools(
                config.tool,
                config.knowledge,
                config.memory,
                user_id=config.metadata.user_id,
            )
        ]  # Construct tools based on configuration (memory and knowledge tools are conditionally added)

        model = self._get_agent_model(config)

        with trace_block("Agno Core Agent Creation"):
            agent = agno.agent.agent.Agent(
                ### Persona ###
                name=config.persona.name,
                role=config.persona.role,
                description=config.persona.description,
                ### Metadata ###
                agent_id=config.metadata.agent_id,
                user_id=config.metadata.user_id,
                session_id=config.metadata.session_id,
                ### Model ###
                model=model,
                ### Memory ###
                # Use mem0 for memory
                ### Knowledge ###
                knowledge=None,
                ### Tools ###
                tools=tools,  # type: ignore
                ### Storage ### # Note: To be replaced by our own session and message tables
                response_model=(ResponseModel if not config.stream else None),
                additional_context=config.additional_context,
            )

        self._agent = agent
        self.config = config
        self.filler_manager = FillerWordsManager(
            chat_filler_words=config.voice_config.chat_filler_words,
            tool_calling_filler_words=config.voice_config.tool_calling_filler_words,
            agent_id=config.metadata.agent_id,
            account_name=config.metadata.account_name,
            chat_filler_words_percentage=config.voice_config.chat_filler_words_percentage,
            tool_calling_filler_words_percentage=config.voice_config.tool_calling_filler_words_percentage,
        )

    async def arun(self, input: Input) -> Output | AsyncIterator[Output]:
        """
        Run the agent with the given input.

        Args:
            input: The input to process with optional history_messages

        Returns:
            Output or AsyncIterator[Output]: The agent's response
        """
        # Handle streaming case
        if not input.stream:
            return await self._arun_with_workflow(input)

        return self._create_traced_stream_iterator(input)

    @agent(name="AgnoAgent")
    async def _arun_with_workflow(self, input: Input) -> Output:
        message, messages = await self._build_model_inputs(input)

        result = await self._agent.arun(
            message,
            messages=messages,
            stream=input.stream,
        )
        # Handle non-streaming case
        response_format = result.content

        if not isinstance(response_format, ResponseModel):
            logger.error(
                (
                    f"Error with getting proper response format:{response_format}\n"
                    f"response type: {type(response_format)}\n"
                    f"agent stream: {self._agent.stream}\n"
                    f"response model: {self._agent.response_model}"
                )
            )
            return Output(content="")

        content = response_format.content
        escalated = response_format.escalated
        closing_conversation = response_format.closing_conversation

        documents = []
        images = []

        return (
            Output(
                content=content,
                documents=documents,
                images=images,
                escalated=escalated,
                closing_conversation=closing_conversation,
            )
            if content is not None
            else Output(content="", documents=documents, images=images)
        )

    def _create_traced_stream_iterator(self, input: Input) -> AsyncIterator[Output]:
        @agent(name="AgnoAgent")
        async def stream_wrapper() -> AsyncIterator[Output]:
            LLMObs.annotate(
                input_data=input,
                tags={
                    "streaming": True,
                },
            )

            output_content = ""
            message, messages = await self._build_model_inputs(input)

            logger.debug(
                f"[AgnoAgent] start getting called at {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                extra={
                    "agent_id": self.config.metadata.agent_id,
                    "account_name": self.config.metadata.account_name,
                },
            )
            send_dd_histogram_metrics(
                "framework_agent.start_streaming",
                input.request_context.request_time,
                [
                    "agent:agno",
                    f"agent_id:{self.config.metadata.agent_id}",
                    f"account_name:{self.config.metadata.account_name}",
                ],
            )

            result = await self._agent.arun(
                message,
                messages=messages,
                stream=input.stream,
            )

            logger.debug(
                f"[AgnoAgent] called with {len(messages) if messages else 'None'} messages, streaming={input.stream}, return_type:{type(result)} at {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                extra={
                    "agent_id": self.config.metadata.agent_id,
                    "account_name": self.config.metadata.account_name,
                },
            )

            try:
                send_dd_histogram_metrics(
                    "framework_agent.waiting_first_chunk",
                    input.request_context.request_time,
                    [
                        "agent:agno",
                        f"agent_id:{self.config.metadata.agent_id}",
                        f"account_name:{self.config.metadata.account_name}",
                    ],
                )
                logger.debug(
                    f"[AgnoAgent] waiting_first_chunk {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                    extra={
                        "agent_id": self.config.metadata.agent_id,
                        "account_name": self.config.metadata.account_name,
                    },
                )

                # Output chat filler words if configured
                filler_words = self.filler_manager.get_chat_filler_for_input(
                    input.content
                )

                if filler_words:
                    filler_output = Output(
                        content=filler_words,
                        documents=[],
                        images=[],
                    )
                    output_content += filler_output.content
                    yield filler_output

                chunk_index = 0
                async for chunk in result:
                    if isinstance(chunk, RunResponseContentEvent):
                        # Skip chunks without valid content
                        content = getattr(chunk, "content", None)
                        if not content:
                            logger.debug(
                                "[AgnoAgent] skipping chunk with empty/None content",
                                extra={
                                    "agent_id": self.config.metadata.agent_id,
                                    "account_name": self.config.metadata.account_name,
                                    "chunk": chunk,
                                },
                            )
                            continue

                        chunk_index += 1
                        if chunk_index == 1:
                            send_dd_histogram_metrics(
                                "framework_agent.received_first_chunk",
                                input.request_context.request_time,
                                [
                                    "agent:agno",
                                    f"agent_id:{self.config.metadata.agent_id}",
                                    f"account_name:{self.config.metadata.account_name}",
                                ],
                            )
                            logger.debug(
                                f"[AgnoAgent] received_first_chunk {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                                extra={
                                    "agent_id": self.config.metadata.agent_id,
                                    "account_name": self.config.metadata.account_name,
                                    "chunk": chunk,
                                },
                            )

                        chunk_output = Output(
                            content=content,
                            documents=[],
                            images=[],
                        )
                        output_content += chunk_output.content
                        yield chunk_output

                    elif isinstance(chunk, ToolCallStartedEvent):
                        # Output filler words when tool execution starts
                        logger.debug(
                            "[AgnoAgent] received tool call started event",
                            extra={
                                "agent_id": self.config.metadata.agent_id,
                                "account_name": self.config.metadata.account_name,
                            },
                        )

                        tool_name = (
                            chunk.tool.tool_name
                            if chunk.tool and chunk.tool.tool_name
                            else "unknown"
                        )
                        tool_filler_words = (
                            self.filler_manager.get_tool_calling_filler_for_input(
                                input.content, tool_name
                            )
                        )

                        if tool_filler_words:
                            tool_filler_output = Output(
                                content=tool_filler_words,
                                documents=[],
                                images=[],
                            )
                            output_content += tool_filler_output.content
                            yield tool_filler_output
                    else:
                        logger.debug(
                            f"[AgnoAgent] received non ResponseContent type chunk: {type(chunk)}",
                            extra={
                                "agent_id": self.config.metadata.agent_id,
                                "account_name": self.config.metadata.account_name,
                                "chunk": chunk,
                            },
                        )

            except Exception as e:
                logger.error(f"Error streaming output: {e}")
                error_output = Output(content="Error streaming output")
                output_content += error_output.content
                yield error_output

            LLMObs.annotate(output_data=output_content)

        return stream_wrapper()

    def _get_agent_model(self, config: AgentConfig):
        model_config = config.model
        if not model_config:
            return build_agno_model(ModelOptions.GPT_4O)
        else:
            model_name = model_config.identifier
            for model_option in ModelOptions:
                if model_name == model_option.model_name:
                    return build_agno_model(model_option)
            logger.warning(f"Failed to load model {model_name}, fallback to gpt-4o.")
            return build_agno_model(ModelOptions.GPT_4O)

    async def _build_model_inputs(
        self, input: Input
    ) -> tuple[Optional[str], Optional[list[Message]]]:
        current_time = datetime.datetime.now(datetime.timezone.utc)

        messages = await self.get_history_messages(input)

        if self.config.memory.enabled:
            mem_content = await get_all_memories(self.config.metadata.user_id)  # type: ignore
            if mem_content and mem_content.strip():
                enhanced_mem_content = f"MEMORY: The following contains important information about your user. Use this context to personalize your responses, remember their preferences, and provide relevant assistance based on their history and needs:\n\n{mem_content}"
                mem_message = Message(role="user", content=enhanced_mem_content)
                messages.append(mem_message)
                logger.debug(f"[PalMemory]: Find user info from memory: {mem_content}")
            else:
                logger.debug("[PalMemory]: No memory content found")
        else:
            logger.debug("[PalMemory]: Memory is disabled, skipping memory fetch")

        send_dd_histogram_metrics(
            "framework_agent.query_history_messages_time_spent",
            current_time,
            [
                f"streaming:{str(input.stream).lower()}",
                f"conversation_id:{self.config.metadata.session_id}",
                "agent:agno",
                f"agent_id:{self.config.metadata.agent_id}",
                f"account_name:{self.config.metadata.account_name}",
            ],
        )

        return None, messages

    async def get_history_messages(self, input: Input) -> list[Message]:
        history_messages = await query_history_messages(
            uuid.UUID(self.config.metadata.session_id), limit=100
        )

        messages = [
            Message(role=msg.role, content=msg.content) for msg in history_messages
        ]

        if len(messages) < 1:
            logger.error(
                "[AgnoAgent] Message history should contain at least 1 message"
            )
        else:
            if messages[-1].content != input.content:
                logger.warning(
                    f"[AgnoAgent] The latest message: {messages[-1].content} should be the current user input: {input.content}"
                )
            else:
                messages = messages[:-1]
        messages.append(Message(role="user", content=input.get_prompt()))
        return messages
