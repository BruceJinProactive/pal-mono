import random
import re
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


class FillerIntent(StrEnum):
    """Intent categories for context-based filler selection."""

    ACTION = "action"
    LOOKUP = "lookup"
    HELP = "help"


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

    # Keyword categories for context-based filler selection
    _KEYWORD_CATEGORIES: ClassVar[dict[str, dict[str, dict[str, list[str]]]]] = {
        "ENGLISH": {
            "action": {
                "keywords": [
                    "order",
                    "book",
                    "reserve",
                    "cancel",
                    "change",
                    "modify",
                    "update",
                    "add",
                    "remove",
                    "make",
                    "set up",
                    "schedule",
                ],
                "chat_fillers": [
                    "Happy to help.",
                    "Let's take a look.",
                    "Here's what I found.",
                    "I can help with that.",
                    "Sure thing.",
                    "Absolutely.",
                ],
                "tool_fillers": [
                    "Let me work on that.",
                    "I'll get that sorted for you right away.",
                    "No problem, I can handle that.",
                    "Consider it done.",
                ],
            },
            "lookup": {
                "keywords": [
                    "check",
                    "find",
                    "search",
                    "status",
                    "where",
                    "when",
                    "what",
                    "how much",
                    "price",
                    "hours",
                    "menu",
                    "available",
                ],
                "chat_fillers": [
                    "Let me check that out for you.",
                    "I'll confirm that for you.",
                    "Let me pull up the details.",
                    "One moment while I check.",
                    "Let me look into this.",
                    "Let me see",
                ],
                "tool_fillers": [
                    "I'm checking, just a moment",
                    "One moment, pulling up details.",
                    "Let me look.",
                    "I'll find that info for you.",
                    "Let me see",
                ],
            },
            "help": {
                "keywords": [
                    "help",
                    "support",
                    "manager",
                    "speak to",
                    "talk to",
                    "problem",
                    "issue",
                    "wrong",
                    "mistake",
                    "complaint",
                ],
                "chat_fillers": [
                    "I can help with that.",
                    "Got it. One moment",
                    "Let me see what I can do.",
                    "Looking into that now.",
                    "Let me pull up the details.",
                    "Let me look into this",
                ],
                "tool_fillers": [
                    "I'm on it, just one moment.",
                    "Reviewing the details now.",
                    "Sorting this out for you.",
                    "Let me pull up the details.",
                ],
            },
        },
        "SPANISH": {
            "action": {
                "keywords": [
                    "ordenar",
                    "pedir",
                    "reservar",
                    "cancelar",
                    "cambiar",
                    "modificar",
                    "actualizar",
                    "agregar",
                    "añadir",
                    "quitar",
                    "eliminar",
                    "hacer",
                    "configurar",
                    "programar",
                ],
                "chat_fillers": [
                    "Entendido, te ayudo con eso.",
                    "Vale, yo me encargo.",
                    "Claro, lo gestiono ahora.",
                    "No hay problema.",
                    "Bien, me ocupo de eso.",
                ],
                "tool_fillers": [
                    "Ya estoy en eso.",
                    "Me pongo con ello.",
                    "Enseguida te lo resuelvo.",
                    "No hay problema, dame un segundo.",
                    "Consideralo hecho.",
                ],
            },
            "lookup": {
                "keywords": [
                    "revisar",
                    "verificar",
                    "buscar",
                    "encontrar",
                    "estado",
                    "dónde",
                    "cuándo",
                    "qué",
                    "cuánto",
                    "precio",
                    "horario",
                    "menú",
                    "disponible",
                ],
                "chat_fillers": [
                    "Buena pregunta, vamos a ver.",
                    "Déjame averiguarlo.",
                    "Puedo revisar eso.",
                    "Déjame ver.",
                    "Déjame echar un vistazo.",
                ],
                "tool_fillers": [
                    "Revisando el sistema.",
                    "Un momento, buscando los detalles.",
                    "Consultando esa información.",
                    "Te busco esa información.",
                    "Déjame ver qué encuentro.",
                ],
            },
            "help": {
                "keywords": [
                    "ayuda",
                    "ayudar",
                    "soporte",
                    "gerente",
                    "encargado",
                    "hablar con",
                    "problema",
                    "mal",
                    "incorrecto",
                    "error",
                    "queja",
                ],
                "chat_fillers": [
                    "Entiendo la situación.",
                    "Entiendo lo que dices.",
                    "Déjame ver qué puedo hacer.",
                    "Estoy aquí para ayudar.",
                    "Vale, vamos a resolverlo.",
                ],
                "tool_fillers": [
                    "Entiendo, vamos a resolverlo.",
                    "En eso estoy.",
                    "Veamos cómo lo solucionamos.",
                    "Lo reviso de inmediato.",
                    "Déjame arreglar esto.",
                ],
            },
        },
        "CHINESE": {
            "action": {
                "keywords": [
                    "点",
                    "订",
                    "下单",
                    "预订",
                    "预约",
                    "订位",
                    "取消",
                    "改",
                    "换",
                    "修改",
                    "更新",
                    "加",
                    "添加",
                    "去掉",
                    "删除",
                    "做",
                    "设置",
                    "安排",
                ],
                "chat_fillers": [
                    "好的，我可以帮您。",
                    "没问题，我来处理。",
                    "可以的，马上办。",
                    "好的，没问题。",
                    "行，我来安排。",
                ],
                "tool_fillers": [
                    "正在处理。",
                    "正在为您处理。",
                    "我马上帮您处理。",
                    "没问题，交给我处理。",
                    "马上为您办理。",
                ],
            },
            "lookup": {
                "keywords": [
                    "查",
                    "看看",
                    "找",
                    "搜",
                    "状态",
                    "哪",
                    "哪里",
                    "什么时候",
                    "几点",
                    "什么",
                    "多少",
                    "价格",
                    "多少钱",
                    "营业时间",
                    "菜单",
                    "有没有",
                    "还有",
                ],
                "chat_fillers": [
                    "好的，我查一下。",
                    "我来帮您确认。",
                    "我可以看看。",
                    "请稍等一下。",
                    "嗯，我帮您查。",
                ],
                "tool_fillers": [
                    "帮您查一下。",
                    "稍等，我查一下详情。",
                    "我看看。",
                    "我帮您找一下。",
                    "我来查查看。",
                ],
            },
            "help": {
                "keywords": [
                    "帮",
                    "帮忙",
                    "客服",
                    "经理",
                    "找人",
                    "跟人说",
                    "问题",
                    "毛病",
                    "错",
                    "搞错",
                    "投诉",
                ],
                "chat_fillers": [
                    "我明白。",
                    "我明白您的意思。",
                    "让我看看能做什么。",
                    "我来帮您。",
                    "好的，我们来解决。",
                ],
                "tool_fillers": [
                    "我明白，咱们来看看怎么解决。",
                    "马上处理。",
                    "我们看看怎么解决。",
                    "我立刻查一下。",
                    "我来帮您处理。",
                ],
            },
        },
    }

    # Question indicators for detecting questions when no keywords match
    _QUESTION_INDICATORS: dict[str, dict[str, list[str]]] = {
        "ENGLISH": {
            "markers": ["?"],
            "starters": [
                "what",
                "when",
                "where",
                "who",
                "why",
                "how",
                "is",
                "are",
                "can",
                "could",
                "would",
                "do",
                "does",
                "did",
                "will",
                "should",
            ],
        },
        "SPANISH": {
            "markers": ["?", "¿"],
            "starters": [
                "qué",
                "cuándo",
                "dónde",
                "quién",
                "por qué",
                "cómo",
                "cuál",
                "cuánto",
                "es",
                "está",
                "puede",
                "puedo",
                "tiene",
                "hay",
                "son",
                "están",
            ],
        },
        "CHINESE": {
            "markers": ["?", "？"],
            "particles": [
                "吗",
                "呢",
                "什么",
                "哪",
                "哪里",
                "几",
                "多少",
                "怎么",
                "为什么",
                "是不是",
                "有没有",
                "能不能",
            ],
        },
    }

    # Fillers for questions when no keyword category matches
    _QUESTION_FILLERS: dict[str, dict[str, list[str]]] = {
        "ENGLISH": {
            "chat_fillers": [
                "Good question.",
                "Let me think about that.",
                "Hmm, let me see.",
                "That's a good one.",
                "Let me find out.",
            ],
            "tool_fillers": [
                "Let's see here...",
                "I'll find out for you.",
                "One second, looking into that.",
                "Let me get an answer for you.",
            ],
        },
        "SPANISH": {
            "chat_fillers": [
                "Buena pregunta.",
                "Déjame pensarlo.",
                "Hmm, déjame ver.",
                "Esa es buena.",
                "Déjame averiguarlo.",
            ],
            "tool_fillers": [
                "Buena pregunta, déjame revisar.",
                "A ver...",
                "Te lo averiguo.",
                "Un segundo, lo estoy revisando.",
                "Déjame conseguirte una respuesta.",
            ],
        },
        "CHINESE": {
            "chat_fillers": [
                "好问题。",
                "让我想想。",
                "嗯，我看看。",
                "这个问题问得好。",
                "我来查一下。",
            ],
            "tool_fillers": [
                "好问题，我查一下。",
                "我看看...",
                "我帮您问一下。",
                "稍等，我查查。",
                "我帮您找答案。",
            ],
        },
    }

    # Fallback fillers when no keywords match and not a question
    _FALLBACK_FILLERS: dict[str, dict[str, list[str]]] = {
        "ENGLISH": {
            "chat_fillers": [
                "Got it.",
                "Okay.",
                "Alright.",
                "Sure.",
                "I see.",
            ],
            "tool_fillers": [
                "Just a moment.",
                "Bear with me for a second.",
                "Hang on a sec.",
                "Okay, let me see.",
                "One moment please.",
            ],
        },
        "SPANISH": {
            "chat_fillers": [
                "Entendido.",
                "Vale.",
                "De acuerdo.",
                "Claro.",
                "Ya veo.",
            ],
            "tool_fillers": [
                "Un momento.",
                "Dame un segundito.",
                "Espera un segundo.",
                "Vale, déjame ver.",
                "Un momento, por favor.",
            ],
        },
        "CHINESE": {
            "chat_fillers": [
                "好的。",
                "嗯。",
                "明白。",
                "可以。",
                "了解。",
            ],
            "tool_fillers": [
                "稍等一下。",
                "请稍等片刻。",
                "等一下。",
                "好的，我看看。",
                "请稍等。",
            ],
        },
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

    def _has_keyword(self, text: str, keyword: str) -> bool:
        """
        Check if keyword exists in text.

        Uses word boundaries for ASCII-only single-word keywords to avoid
        partial matches (e.g., "order" shouldn't match "border").
        Uses substring matching for multi-word phrases and non-ASCII keywords
        (CJK characters) since regex word boundaries don't work for those.

        Args:
            text: The text to search in
            keyword: The keyword to search for

        Returns:
            True if keyword is found, False otherwise
        """
        keyword_lower = keyword.lower()
        text_lower = text.lower()

        # ASCII-only single words: use \b word boundary
        if keyword_lower.isascii() and " " not in keyword_lower:
            return bool(re.search(rf"\b{re.escape(keyword_lower)}\b", text_lower))

        # Multi-word phrases or non-ASCII (CJK): use substring match
        return keyword_lower in text_lower

    def _classify_by_keywords(self, text: str, language: str) -> str | None:
        """
        Classify input text into an intent category based on keyword matching.

        Args:
            text: The input text to classify (should be lowercase)
            language: The language code (e.g., "ENGLISH", "SPANISH", "CHINESE")

        Returns:
            Intent category ("action", "lookup", "help") or None if no match
        """
        categories = self._KEYWORD_CATEGORIES.get(language, {})
        if not categories:
            return None

        # Check categories in priority order: action > lookup > help
        for intent in [FillerIntent.ACTION, FillerIntent.LOOKUP, FillerIntent.HELP]:
            category = categories.get(intent.value, {})
            keywords = category.get("keywords", [])
            for keyword in keywords:
                if self._has_keyword(text, keyword):
                    logger.debug(
                        f"[FillerWordsManager] Matched keyword '{keyword}' to intent '{intent.value}'",
                        extra={
                            "agent_id": self.agent_id,
                            "account_name": self.account_name,
                            "language": language,
                            "intent": intent.value,
                        },
                    )
                    return intent.value
        return None

    def _is_question(self, text: str, language: str) -> bool:
        """
        Detect if the input text is a question.

        Args:
            text: The input text to check
            language: The language code (e.g., "ENGLISH", "SPANISH", "CHINESE")

        Returns:
            True if text appears to be a question, False otherwise
        """
        indicators = self._QUESTION_INDICATORS.get(language, {})
        if not indicators:
            return False

        # Check for question markers (fast path)
        markers = indicators.get("markers", [])
        if any(marker in text for marker in markers):
            return True

        text_lower = text.lower().strip()

        # Check for question starters (English, Spanish)
        # Use word boundary to avoid partial matches (e.g., "is" shouldn't match "island")
        starters = indicators.get("starters", [])
        if any(re.match(rf"{starter}\b", text_lower) for starter in starters):
            return True

        # Check for question particles (Chinese)
        particles = indicators.get("particles", [])
        if any(particle in text for particle in particles):
            return True

        return False

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
        Generate a filler phrase using context-based selection.

        Selection priority:
        1. Keyword matching (action > lookup > help)
        2. Question detection
        3. Fallback

        Args:
            language: The language code/name for which to get filler words
            filler_type: Type of filler words (FillerType enum)
            input_content: The user input text, used to determine context

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

        # Determine which filler key to use based on filler_type
        filler_key = (
            "chat_fillers" if filler_type == FillerType.CHAT else "tool_fillers"
        )

        text_lower = input_content.lower().strip()
        selected_filler = None
        selection_reason = "fallback"

        # Stage 1: Keyword-based classification
        intent = self._classify_by_keywords(text_lower, language)
        if intent:
            category = self._KEYWORD_CATEGORIES.get(language, {}).get(intent, {})
            fillers = category.get(filler_key, [])
            if fillers:
                selected_filler = random.choice(fillers)
                selection_reason = f"keyword:{intent}"

        # Stage 2: Question detection
        if not selected_filler and self._is_question(input_content, language):
            question_fillers = self._QUESTION_FILLERS.get(language, {}).get(
                filler_key, []
            )
            if question_fillers:
                selected_filler = random.choice(question_fillers)
                selection_reason = "question"

        # Stage 3: Fallback
        if not selected_filler:
            fallback_fillers = self._FALLBACK_FILLERS.get(language, {}).get(
                filler_key, []
            )
            if fallback_fillers:
                selected_filler = random.choice(fallback_fillers)
                selection_reason = "fallback"

        if not selected_filler:
            logger.debug(
                f"[FillerWordsManager] No fillers available for {language}/{filler_type}",
                extra={
                    "agent_id": self.agent_id,
                    "account_name": self.account_name,
                    "language": language,
                    "filler_type": filler_type.value,
                },
            )
            return ""

        logger.debug(
            f"[FillerWordsManager] Selected {filler_type} filler for {language}: '{selected_filler}' "
            f"(reason={selection_reason})",
            extra={
                "agent_id": self.agent_id,
                "account_name": self.account_name,
                "language": language,
                "filler_type": filler_type.value,
                "selection_reason": selection_reason,
            },
        )

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
        # Check percentage threshold
        if filler_type == FillerType.CHAT:
            percentage_threshold = self.chat_filler_words_percentage
            type_name = "chat"
        elif filler_type == FillerType.TOOL_CALLING:
            percentage_threshold = self.tool_calling_filler_words_percentage
            type_name = "tool calling"
        else:
            logger.error(f"[FillerWordsManager] Unknown filler type: {filler_type}")
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
