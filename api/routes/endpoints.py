from dataclasses import dataclass


@dataclass
class ApiEndpoints:
    ADMIN: str = "/admin"
    CHAT: str = "/chat"
    HEALTH: str = "/health"
    PING: str = "/ping"
    ASSETS: str = "/assets"
    INTEGRATIONS: str = "/integrations"
    OPERATION: str = "/operation"
    CATERING: str = "/catering"
    TELEPHONY: str = "/telephony"
    EVAL: str = "/eval"
    SNAPSHOTS: str = "/snapshots"


endpoints = ApiEndpoints()
