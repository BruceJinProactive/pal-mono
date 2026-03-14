"""pal-agents tool registry.

Maps ``ProjectIntegration.tool_name`` to a pal-agents Spec field + builder
function.  The generic dispatch in ``_implementation._build_specs_from_project_integrations``
queries project integrations, resolves credentials, and calls the builder
registered here.

To add a new tool:
1. Write a builder function::

       def _build_appname_spec(
           config: dict[str, Any],
           store_identifier: str,
           client_id: str | None,
           client_secret: str | None,
       ) -> AppnameSpec:
           ...

2. Add one entry to ``PAL_AGENT_TOOL_REGISTRY``::
       "appname_v1": PalAgentToolEntry(spec_field="appname", builder=_build_appname_spec),

3. In ``_implementation.construct_agent_spec()``, add a fallback::
       appname_spec = pi_specs.get("appname") or _build_appname_spec_from_raw_config(...)

4. Wire ``appname_spec`` through ``_agent_config_to_spec()`` into ``Spec(appname=...)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pal_agents.spec import AdoraSpec

# ========== Registry infrastructure ==========


@dataclass(frozen=True, slots=True)
class PalAgentToolEntry:
    """Registry entry mapping a ProjectIntegration tool_name to a spec builder."""

    spec_field: str  # kwarg name on Spec(), e.g. "adora"
    builder: Callable[
        [dict[str, Any], str, str | None, str | None], Any
    ]  # (config, store_identifier, client_id, client_secret) -> spec


# ========== Shared helpers ==========


def merge_auth_with_credentials(
    auth_config: dict[str, Any] | None,
    client_id: str | None,
    client_secret: str | None,
    default_token_url: str | None = None,
) -> dict[str, Any] | None:
    """Merge auth structure from config with credentials from Integration.

    The config provides the auth shape (type, etc.) and the Integration record
    provides actual secret values (client_id, client_secret).

    If no auth config is provided but credentials exist and a *default_token_url*
    is given, builds a rotating bearer auth dict automatically. The caller should
    handle token_url fallback logic (e.g., config.get("token_url") or DEFAULT_URL).
    """
    if not client_id and not client_secret:
        return auth_config

    if auth_config is None:
        if default_token_url and client_id and client_secret:
            return {
                "type": "bearer",
                "rotation": {
                    "enabled": True,
                    "token_url": default_token_url,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            }
        return None

    auth = dict(auth_config)
    auth_type = auth.get("type")

    if auth_type == "bearer" and isinstance(auth.get("rotation"), dict):
        rotation = dict(auth["rotation"])
        if client_id:
            rotation["client_id"] = client_id
        if client_secret:
            rotation["client_secret"] = client_secret
        if default_token_url and "token_url" not in rotation:
            rotation["token_url"] = default_token_url
        auth["rotation"] = rotation
    elif auth_type == "basic":
        if client_id:
            auth["username"] = client_id
        if client_secret:
            auth["password"] = client_secret

    return auth


# ========== Adora v3 builder ==========

_ADORA_SPEC_FIELDS = [
    "menu_data",
    "coupon_data",
    "base_url",
    "allowed_paths",
    "timeout",
    "inject",
    "store_id",
    "customer_email",
    "tool_name",
    "debug",
    "force_payment_link",
    "no_delivery_entries",
]

_ADORA_DEFAULT_TOKEN_URL = "https://identity.adorapos.net/connect/token"


def _build_adora_v3_spec(
    config: dict[str, Any],
    store_identifier: str,
    client_id: str | None,
    client_secret: str | None,
) -> AdoraSpec:
    """Build an AdoraSpec from ProjectIntegration config + Integration credentials."""
    kwargs: dict[str, Any] = {"enabled": True}
    for field in _ADORA_SPEC_FIELDS:
        if field in config:
            kwargs[field] = config[field]

    if store_identifier:
        kwargs["store_id"] = store_identifier

    auth = merge_auth_with_credentials(
        config.get("auth"),
        client_id,
        client_secret,
        default_token_url=config.get("token_url") or _ADORA_DEFAULT_TOKEN_URL,
    )
    if auth is not None:
        kwargs["auth"] = auth

    return AdoraSpec(**kwargs)


# ========== Registry ==========

PAL_AGENT_TOOL_REGISTRY: dict[str, PalAgentToolEntry] = {
    "adora_v3": PalAgentToolEntry(spec_field="adora", builder=_build_adora_v3_spec),
}
