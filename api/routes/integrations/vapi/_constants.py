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
        "voice_id": "3a63e2d1-1c1e-425d-8e79-5100bc910e90",  # chinese call center woman
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
    "english": lambda agent_name, account_name: f"Hello! This is {agent_name} from {account_name}. I'm here to help you in English. How can I assist you today?",
    "spanish": lambda agent_name, account_name: f"¡Hola! Soy {agent_name} de {account_name}. Estoy aquí para ayudarte en español. ¿En qué puedo asistirte hoy?",
    "chinese": lambda agent_name, account_name: f"您好！我是{account_name}的{agent_name}。我可以用中文为您提供帮助。请问有什么需要我协助的吗？",
}
