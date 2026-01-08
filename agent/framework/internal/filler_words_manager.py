import os
import random
from enum import StrEnum
from typing import ClassVar, Optional, Protocol, cast

from lingua import Language, LanguageDetectorBuilder

from utils.log import logger


class LanguageDetectorProtocol(Protocol):
    """Protocol for lingua LanguageDetector to enable proper typing."""

    def detect_multiple_languages_of(self, text: str) -> list:
        """Detect multiple languages in the given text."""
        ...

    def compute_language_confidence(self, text: str, language: Language) -> float:
        """Compute the confidence value for the given language and input text."""
        ...


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

    # Class-level cached language detector
    _LANGUAGE_DETECTOR: ClassVar[Optional[LanguageDetectorProtocol]] = None

    # Input length threshold for filler word selection (from env var or default)
    try:
        _raw_threshold = int(os.getenv("FILLER_INPUT_LENGTH_THRESHOLD", "35"))
        if _raw_threshold < 1:
            _INPUT_LENGTH_THRESHOLD = 35
            logger.warning(
                "FILLER_INPUT_LENGTH_THRESHOLD must be positive, using default: 35"
            )
        else:
            _INPUT_LENGTH_THRESHOLD = _raw_threshold
    except ValueError:
        _INPUT_LENGTH_THRESHOLD = 35
        logger.warning(
            "FILLER_INPUT_LENGTH_THRESHOLD must be a valid integer, using default: 35"
        )

    # Hardcoded filler words lists
    _CHAT_FILLER_WORDS: dict[str, list[str]] = {
        "CHINESE": [
            "好的，我来帮您查一下。",
            "明白了，谢谢您告诉我。",
            "请稍等，我核实一下。",
            "没问题，我帮您看一下。",
            "嗯，我知道您的意思了。",
            "了解，我这就去看看。",
            "好的，请给我一点时间确认。",
        ],
        "ENGLISH": [
            "OK. Let me check on it.",
            "Got it, thanks for letting me know.",
            "One second, let me check on that.",
            "Sure thing, let me check for you.",
            "Alright, I can look into that for you.",
            "Understood, let me look into that for you.",
            "Okay, let's see what we can do here.",
            "Okay, so…",
            "Alright, so…",
            "Let me see…",
            "One moment…",
            "Just a second…",
            "Let me check that…",
            "Give me a sec…",
            "Hang on one sec…",
            "Let me take a look…",
            "Okay, hang on…",
            "Yeah, one second…",
        ],
        "SPANISH": [
            "Vale, déjame revisarlo.",
            "Perfecto, gracias por avisar.",
            "Un momento, lo reviso enseguida.",
            "Claro, déjame comprobarlo por ti.",
            "De acuerdo, puedo mirarlo para ti.",
            "Ah, ya entiendo lo que dices.",
            "Entendido, lo reviso en un momento.",
        ],
    }
    _TOOL_CALLING_FILLER_WORDS: dict[str, list[str]] = {
        "CHINESE": [
            "我正在处理，请稍等。",
            "再给我几秒钟。",
            "谢谢您的耐心，我正在处理。",
            "请再稍等一下。",
            "让我帮您查一下。",
            "现在就帮您处理。",
            "请再稍等片刻。",
            "我正在帮您确认。",
            "请再给我一点时间。",
        ],
        "ENGLISH": [
            "I am working on it.",
            "Give me a few seconds.",
            "Thanks for your patience. I am working on it.",
            "Just a moment, please.",
            "Let me check that for you.",
            "Working on it now.",
            "Hang on a moment.",
            "I'm checking that for you now.",
            "Give me just a sec.",
            "Alright, looking that up for you.",
        ],
        "SPANISH": [
            "Ya estoy en eso.",
            "Dame unos segundos.",
            "Gracias por tu paciencia, lo estoy revisando.",
            "Un momento, por favor.",
            "Déjame comprobar eso por ti.",
            "Lo estoy revisando ahora mismo.",
            "Espera un momento.",
            "Estoy mirando eso en este instante.",
            "Dame solo un segundo.",
            "Vale, estoy buscando esa información para ti.",
        ],
    }

    def __init__(
        self,
        agent_id: str,
        account_name: str,
        chat_filler_words_percentage: int = 80,
        tool_calling_filler_words_percentage: int = 80,
    ):
        self.agent_id = agent_id
        self.account_name = account_name
        self.chat_filler_words_percentage = chat_filler_words_percentage
        self.tool_calling_filler_words_percentage = tool_calling_filler_words_percentage

    def _build_language_detector(self):
        """
        Build a language detector with supported languages.
        Uses class-level caching to avoid expensive construction on every call.

        Returns:
            LanguageDetector: Configured language detector
        """
        if FillerWordsManager._LANGUAGE_DETECTOR is None:
            FillerWordsManager._LANGUAGE_DETECTOR = cast(
                LanguageDetectorProtocol,
                LanguageDetectorBuilder.from_languages(
                    *self._SUPPORTED_LANGUAGES
                ).build(),
            )
        return FillerWordsManager._LANGUAGE_DETECTOR

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
            language_detector = self._build_language_detector()
            detected_languages = language_detector.detect_multiple_languages_of(
                input_content
            )

            # Filter languages based on confidence threshold
            filtered_languages = []
            for detected_language in detected_languages:
                language = detected_language.language
                confidence_value = language_detector.compute_language_confidence(
                    input_content, language
                )

                if confidence_value >= 0.5:
                    filtered_languages.append(language)
                else:
                    logger.debug(
                        f"[FillerWordsManager] Filtered out {language.name} due to low confidence: {confidence_value:.2f}",
                        extra={
                            "agent_id": self.agent_id,
                            "account_name": self.account_name,
                            "language": language.name,
                            "confidence": confidence_value,
                        },
                    )

            return filtered_languages
        except Exception as e:
            logger.error(f"[FillerWordsManager] Language detection failed: {e}")
            return []

    def get_filler_words(
        self, language: str, filler_type: FillerType, input_content: str = ""
    ) -> str:
        """
        Generate a filler phrase from configured options for a specific language and type.
        Selects filler length based on input content length using median-based pool splitting.

        Args:
            language: The language code/name for which to get filler words
            filler_type: Type of filler words (FillerType enum)
            input_content: The user input text, used to determine filler length

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
            filler_words_dict = self._CHAT_FILLER_WORDS
        elif filler_type == FillerType.TOOL_CALLING:
            filler_words_dict = self._TOOL_CALLING_FILLER_WORDS
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

        # Sort fillers by length and find median length for pool splitting
        sorted_fillers = sorted(language_filler_words, key=len)
        median_length = len(sorted_fillers[len(sorted_fillers) // 2])

        # Build appropriate pool based on input length vs threshold
        if len(input_content.strip()) < self._INPUT_LENGTH_THRESHOLD:
            pool = [f for f in language_filler_words if len(f) <= median_length]
        else:
            pool = [f for f in language_filler_words if len(f) >= median_length]

        # Select a random filler from the pool
        selected_filler = random.choice(pool)
        logger.debug(
            f"[FillerWordsManager] Selected {filler_type} filler for {language}: '{selected_filler}' "
            f"(input_length={len(input_content)}, threshold={self._INPUT_LENGTH_THRESHOLD}, pool_size={len(pool)})"
        )

        # Empty string in config to control the probability
        if not selected_filler:
            return ""
        return selected_filler + " <flush />"

    def is_language_supported(self, language: str) -> bool:
        """Check if a language is supported for filler words"""
        supported_language_names = {lang.name for lang in self._SUPPORTED_LANGUAGES}
        return language in supported_language_names

    def _get_filler_for_input(
        self, input_content: str, filler_type: FillerType, tool_name: str = "unknown"
    ) -> str:
        """
        Internal method to get filler words with automatic language detection and decision logic.

        Args:
            input_content: The input text to analyze
            filler_type: Type of filler words to get
            tool_name: Name of the tool being called (for logging)

        Returns:
            Filler words string or empty string if should be skipped
        """
        # Get the appropriate filler words dictionary based on type
        if filler_type == FillerType.CHAT:
            filler_words_dict = self._CHAT_FILLER_WORDS
            percentage_threshold = self.chat_filler_words_percentage
            type_name = "chat"
        elif filler_type == FillerType.TOOL_CALLING:
            filler_words_dict = self._TOOL_CALLING_FILLER_WORDS
            percentage_threshold = self.tool_calling_filler_words_percentage
            type_name = "tool calling"
        else:
            logger.error(f"[FillerWordsManager] Unknown filler type: {filler_type}")
            return ""

        if not filler_words_dict:
            logger.debug(
                f"[FillerWordsManager] No {type_name} filler words configured",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                },
            )
            return ""

        if random.randint(1, 100) > percentage_threshold:
            logger.debug(
                f"[FillerWordsManager] Skipping {type_name} filler words due to possibility ({percentage_threshold}%)",
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
                detected_language.name, filler_type, input_content
            )

            if filler_words:
                log_extra = {
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                    "detected_language": detected_language.name,
                }
                if filler_type == FillerType.TOOL_CALLING:
                    log_extra["tool_name"] = tool_name

                logger.debug(
                    f"[FillerWordsManager] {type_name.title()} filler outputted: {filler_words}",
                    extra=log_extra,
                )
            return filler_words
        else:
            log_extra = {
                "agent_id": self.agent_id,
                "account_name": self.account_name,
                "detected_languages": [lang.name for lang in detected_languages],
            }
            if filler_type == FillerType.TOOL_CALLING:
                log_extra["tool_name"] = tool_name

            logger.debug(
                f"[FillerWordsManager] Skipping {type_name} filler words due to multilingual input or detection failure",
                extra=log_extra,
            )
            return ""

    def get_chat_filler_for_input(self, input_content: str) -> str:
        """
        Get chat filler words with automatic language detection and decision logic.

        Args:
            input_content: The input text to analyze

        Returns:
            Filler words string or empty string if should be skipped
        """
        return self._get_filler_for_input(input_content, FillerType.CHAT)

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
        return self._get_filler_for_input(
            input_content, FillerType.TOOL_CALLING, tool_name
        )
