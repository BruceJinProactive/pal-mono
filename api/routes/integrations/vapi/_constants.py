from db.tables.agents import SpeechRate

# VAPI Headers
VAPI_SECRET_HEADER = "X-VAPI-SIGNATURE"
VAPI_TIMESTAMP_HEADER = "X-VAPI-TIMESTAMP"

# Default Voice ID
SPORTSMAN_VOICE_ID = "ed81fd13-2016-4a49-8fe3-c0d2761695fc"

# Cartesia voice speed mapping
CARTESIA_SPEED_MAPPING = {
    SpeechRate.slowest: "slowest",
    SpeechRate.slower: "slow",
    SpeechRate.normal: "normal",
    SpeechRate.faster: "fast",
    SpeechRate.fastest: "fastest",
}

# Language-specific voice IDs and configurations
LANGUAGE_VOICE_CONFIGS = {
    "english": {
        "voice_id": "ed81fd13-2016-4a49-8fe3-c0d2761695fc",  # sportsman voice
        "voice_model": "sonic-2",
    },
    "spanish": {
        "voice_id": "db832ebd-3cb6-42e7-9d47-912b425adbaa",  # young spanish-speaking woman
        "voice_model": "sonic-2",
    },
    "chinese": {
        "voice_id": "7a5d4663-88ae-47b7-808e-8f9b9ee4127b",  # Chen
        "voice_model": "sonic-2",
    },
}

# Language-specific say node configurations
LANGUAGE_SAY_CONFIGS = {
    "english": {
        "prompt": "Perfect! Let me connect you to our English support.",
    },
    "spanish": {
        "prompt": "¡Perfecto! Te conecto con nuestro soporte en español.",
    },
    "chinese": {
        "prompt": "好的！让我为您连接到我们的中文客服。",
    },
}

# Language-specific first messages for squad assistants
FIRST_MESSAGES = {
    "english": "Hey! Let me know how I can help.",
    "spanish": "¡Qué onda! ¿En qué te puedo ayudar?",
    "chinese": "嘿！有啥需要我帮忙的不？",
}
