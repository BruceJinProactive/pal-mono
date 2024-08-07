from dataclasses import dataclass


@dataclass
class ApiEndpoints:
    PING: str = "/ping"
    HEALTH: str = "/health"
    CHAT: str = "/chat"
    ASSISTANTS: str = "/assistants"
    SENDBLUE: str = "/webhooks/sendblue"


endpoints = ApiEndpoints()
