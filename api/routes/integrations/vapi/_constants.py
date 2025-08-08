from db.tables.agents import SpeechRate

# ============================================================================
# GENERAL VAPI CONSTANTS (used across multiple files)
# ============================================================================

# VAPI Headers (_utils.py, _implementation.py)
VAPI_SECRET_HEADER = "X-VAPI-SIGNATURE"
VAPI_TIMESTAMP_HEADER = "X-VAPI-TIMESTAMP"

# Default Voice ID (_utils.py, _squad.py, _workflow.py)
SPORTSMAN_VOICE_ID = "ed81fd13-2016-4a49-8fe3-c0d2761695fc"

# Default API settings (_squad.py, _workflow.py)
DEFAULT_SILENCE_TIMEOUT = 60

# Cartesia voice speed mapping (_utils.py)
CARTESIA_SPEED_MAPPING = {
    SpeechRate.slowest: "slowest",
    SpeechRate.slower: "slow",
    SpeechRate.normal: "normal",
    SpeechRate.faster: "fast",
    SpeechRate.fastest: "fastest",
}


# ============================================================================
# ASSISTANT NAMES
# ============================================================================

TRIAGE_ASSISTANT_NAME = "triage_assistant"
ENGLISH_ASSISTANT_NAME = "english_assistant"
SPANISH_ASSISTANT_NAME = "spanish_assistant"
CHINESE_ASSISTANT_NAME = "chinese_assistant"

# ============================================================================
# DEFAULT MULTILINGUAL SQUAD CONFIGURATION
# ============================================================================

# Default multilingual squad configuration
DEFAULT_MULTILINGUAL_SQUAD_CONFIG = {
    "triage_assistant": {
        "name": TRIAGE_ASSISTANT_NAME,
        "transcriber": {
            "provider": "google",
            "model": "gemini-2.5-flash",
            "language": "Multilingual",
        },
        "voice": {
            "voice_id": SPORTSMAN_VOICE_ID,
            "voice_model": "sonic-2",
            "provider": "cartesia",
        },
        "model": {"provider": "openai", "model": "gpt-4o"},
        "first_message": "Hello! I can help you in English, español, or 中文. Please let me know which language you prefer, and I'll connect you with the right specialist.",
        "transfer_mode": "swap-system-message-in-history",
    },
    "language_assistants": {
        "english": {
            "assistant_name": ENGLISH_ASSISTANT_NAME,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-3",
                "language": "en-US",
            },
            "voice": {
                "voice_id": "ed81fd13-2016-4a49-8fe3-c0d2761695fc",
                "voice_model": "sonic-2",
                "provider": "cartesia",
            },
            "first_message": "Let me know how I can help.",
            "transfer_message": "Got it!",
            "transfer_description": "Transfer to English-speaking assistant when customer prefers English or uses English language.",
        },
        "spanish": {
            "assistant_name": SPANISH_ASSISTANT_NAME,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "es",
            },
            "voice": {
                "voice_id": "db832ebd-3cb6-42e7-9d47-912b425adbaa",
                "voice_model": "sonic-2",
                "provider": "cartesia",
            },
            "first_message": "Hola, ¿en qué puedo ayudarte?",
            "transfer_message": "Perfecto, te conecto con alguien que te puede ayudar en español. Un momentito.",
            "transfer_description": "Transfer to Spanish-speaking assistant when customer prefers Spanish, says 'español', or uses Spanish language.",
        },
        "chinese": {
            "assistant_name": CHINESE_ASSISTANT_NAME,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "zh-CN",
            },
            "voice": {
                "voice_id": "7a5d4663-88ae-47b7-808e-8f9b9ee4127b",
                "voice_model": "sonic-2",
                "provider": "cartesia",
            },
            "first_message": "Hello，有什么我能帮您?",
            "transfer_message": "正在为您安排中文服务，请稍候片刻。",
            "transfer_description": "Transfer to Chinese-speaking assistant when customer prefers Chinese, says '中文', uses Chinese characters, or indicates Chinese language preference.",
        },
    },
}
