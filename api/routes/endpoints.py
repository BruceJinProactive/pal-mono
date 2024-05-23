from dataclasses import dataclass


@dataclass
class ApiEndpoints:
    PING: str = "/ping"
    HEALTH: str = "/health"
    ASSISTANTS: str = "/assistants"
    SENDBLUE: str = "/webhooks/sendblue"

endpoints = ApiEndpoints()
