from db.tables.agents import SpeechRate

# ============================================================================
# GENERAL VAPI CONSTANTS (used across multiple files)
# ============================================================================

# VAPI Headers (_utils.py, _implementation.py)
VAPI_SECRET_HEADER = "X-VAPI-SIGNATURE"
VAPI_TIMESTAMP_HEADER = "X-VAPI-TIMESTAMP"

# Default Voice ID (_utils.py, _squad.py, _workflow.py)
SPORTSMAN_VOICE_ID = "ed81fd13-2016-4a49-8fe3-c0d2761695fc"


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
# CALL ANALYSIS PROMPT
# ============================================================================

# Structured data analysis prompt for call evaluation
# TODO: move after we have a proper analysis plan config
CALL_ANALYSIS_PROMPT = """1. Call Purpose
Identify all the main reasons for the customer's call.
	- store_info: Questions about store operations such as hours, pricing, location/directions, parking, or store policies.
	- menu_info: General inquiries about the menu (items, ingredients, portion sizes, pricing) without placing an order.
	- ordering: Calls where the customer is placing or modifying a food order directly with the store.
	- reservation: Requests to reserve a table at the store.
	- waitlist: Calls to join, check, or manage the restaurant's waitlist.
	- takeout_issue: Issues specifically related to takeout orders (e.g., delays, missing items, pickup problems).
	- third_party_order: Questions or issues about orders placed via third-party apps (DoorDash, UberEats, etc.).
	- customer_service: General customer service inquiries not tied to a specific order (e.g., feedback, inquiries about promotions).
	- complaint_service: Complaints about service quality (e.g., staff interactions, slow service, rude behavior).
	- complaint_food_safety: Serious complaints about food safety (e.g., food poisoning, contamination, allergies mishandled).
	- dietary_specific: Inquiries about dietary restrictions or requirements (e.g., gluten-free, vegan, nut-free).
	- lost_and_found: Calls about lost or forgotten items at the store.
	- reservation_change: Requests to modify or cancel an existing reservation.
	- other: Any call purpose that does not fit the categories above.

2. Language Spoken
Determine the *primary* language the customer spoke during the call. Choose exactly one from the options below:
	- english: Customer primarily spoke English
	- french: Customer primarily spoke French
	- spanish: Customer primarily spoke Spanish
	- chinese: Customer primarily spoke Chinese
	- other: Any language that does not fit the categories above.

3. User Satisfaction (Overall)
Assess the customer's overall satisfaction. Choose exactly one from this list:
["positive","neutral","negative"]
	- positive: Customer's issues or inquiries were mostly resolved, or customer confirms resolution and expresses appreciation after resolution (e.g., "that helps, thanks", "perfect").
	- negative: Customer's main issues and inquiries were not met and call ends without an acceptable alternative, or customer expresses dissatisfaction (e.g., "that's not helpful", "I'm frustrated", "this is ridiculous").
	- neutral: Customer's issues or inquiries were partially resolved or transferred, purely informational with no clear success signal, too little content (greeting only), dropped calls, silence, or customer hangs up mid-flow after unmet goal.

4. Explanation of Satisfaction
Write 1–2 sentences explaining why you chose the satisfaction rating.

Output Rules:
You are an evaluation assistant. You must ONLY output valid JSON.
You are NOT allowed to invent or use values outside of the enums below.
If the call does not match any category, you must choose "other".

Valid CallPurpose values (list, multiple allowed, but "other" can only be used once and never combined with other categories):
["store_info","menu_info","ordering","reservation","waitlist","takeout_issue","third_party_order","customer_service","complaint_service","complaint_food_safety","dietary_specific","lost_and_found","reservation_change","other"]

Valid Language Spoken values (exactly one):
["english","french","spanish","chinese","other"]

Valid UserSatisfaction values (exactly one):
["positive","neutral","negative"]

Output MUST be valid JSON in this exact schema:
{
  "call_purpose": ["ordering"],
  "language_spoken": "english",
  "user_satisfaction": "positive",
  "explanation": "One or two plain sentences here."
}"""

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
