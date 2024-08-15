from dataclasses import dataclass


@dataclass
class ApiEndpoints:
    ADMIN: str = "/admin"
    CHAT: str = "/chat"
    HEALTH: str = "/health"
    PING: str = "/ping"


endpoints = ApiEndpoints()
