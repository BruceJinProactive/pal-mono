"""Tool loading and execution for OpenAI Realtime voice sessions.

Handles three tool sources:
- Agno tools: Legacy toolkit-based tools from agent raw_config
- PAL-agent provider tools: toast_v3, adora_v3, olo_v1 via pal-agents providers
- Executor dispatch: Routes tool calls from OpenAI to the correct handler
"""

import asyncio
import inspect
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import ProjectIntegration
from utils.log import logger

if TYPE_CHECKING:
    from agno.tools.function import Function

    from agent.tool import ToolConfig


def build_agno_tools(
    tool_config: "ToolConfig",
) -> tuple[list[dict], dict[str, "Function"]]:
    """Load Agno toolkit tools from agent configuration."""
    from tools.registry import tool_registry

    tools: list[dict] = []
    executors: dict[str, "Function"] = {}

    for identifier in tool_config.identifiers:
        try:
            toolkit = tool_registry.get_tool(identifier, tool_config.metadata)
        except Exception as e:
            logger.error(
                f"[REALTIME] Failed to instantiate tool: {identifier.tool_name}",
                extra={"error": str(e)},
                exc_info=True,
            )
            continue
        if not toolkit:
            logger.warning(
                f"[REALTIME] Tool not found in registry: {identifier.tool_name}"
            )
            continue

        for func_name, func in toolkit.functions.items():
            if not func.entrypoint:
                logger.warning(
                    "[REALTIME] Skipping tool without entrypoint: %s", func_name
                )
                continue
            func.process_entrypoint()
            tools.append(
                {
                    "type": "function",
                    "name": func_name,
                    "description": func.description or "",
                    "parameters": func.parameters,
                }
            )
            executors[func_name] = func

    logger.info(
        "[REALTIME] Loaded %d tool function(s): %s",
        len(tools),
        [t["name"] for t in tools],
    )
    return tools, executors


async def build_pal_agent_provider_tools(
    session: AsyncSession,
    project_id: uuid.UUID,
    caller_id: str | None,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    project_timezone: str | None,
) -> tuple[list[dict], dict[str, Callable]]:
    """Load pal-agents provider tools for realtime sessions.

    Instantiates providers from ProjectIntegration config and returns tool schemas
    plus executors. Lookup tools use real functions; ordering tools are log-only.
    """
    from db.tables.integration import Integration
    from services.agent_service._implementation import _resolve_integration_credentials
    from services.agent_service._pal_agent_tool_registry import PAL_AGENT_TOOL_REGISTRY

    registered_names = list(PAL_AGENT_TOOL_REGISTRY.keys())
    if not registered_names:
        return [], {}

    pi_result = await session.execute(
        select(ProjectIntegration).filter(
            ProjectIntegration.project_id == project_id,
            ProjectIntegration.tool_name.in_(registered_names),
        )
    )
    integrations = list(pi_result.scalars())
    if not integrations:
        return [], {}

    tools: list[dict] = []
    executors: dict[str, Callable] = {}

    for pi in integrations:
        if not pi.tool_name:
            continue
        entry = PAL_AGENT_TOOL_REGISTRY.get(pi.tool_name)
        if not entry:
            continue

        try:
            int_result = await session.execute(
                select(Integration).filter(Integration.id == pi.integration_id)
            )
            integration_record = int_result.scalar_one_or_none()
            client_id, client_secret, parsed_secrets = (
                await _resolve_integration_credentials(integration_record)
            )

            spec = entry.builder(
                dict(pi.config or {}),
                pi.store_identifier or "",
                client_id,
                client_secret,
                parsed_secrets,
            )

            provider_tools: list[dict[str, Any]] = []
            if entry.spec_field == "toast":
                from pal_agents.providers.toast._implementation import Toast

                provider = Toast(spec)
                provider_tools = provider.as_tool()
            elif entry.spec_field == "adora":
                from pal_agents.providers.adora._implementation import Adora

                adora_provider = Adora(spec)
                adora_tool_output = adora_provider.as_tool()
                if isinstance(adora_tool_output, list):
                    provider_tools = adora_tool_output
                else:
                    provider_tools = [adora_tool_output]
            elif entry.spec_field == "olo":
                from pal_agents.providers.olo._implementation import Olo

                olo_tool_output = Olo(spec).as_tool()
                if isinstance(olo_tool_output, list):
                    provider_tools = olo_tool_output
                else:
                    provider_tools = [olo_tool_output]
            else:
                continue
        except Exception as e:
            logger.error(
                "[REALTIME] Skipping PAL integration due to build error",
                extra={"tool_name": pi.tool_name, "error": str(e)},
                exc_info=True,
            )
            continue

        for tool_def in provider_tools:
            tool_name: str = tool_def["name"]
            tools.append(
                {
                    "type": "function",
                    "name": tool_name,
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {}),
                }
            )

            tool_fn = tool_def.get("function")

            def _make_executor(
                name: str,
                fn: Callable[..., Any] | None,
            ) -> Callable[..., Awaitable[str]]:
                async def _executor(**kwargs: object) -> str:
                    logger.info(
                        "[REALTIME.PAL_TOOL] %s",
                        name,
                        extra={"tool_name": name, "arguments": kwargs},
                    )
                    if fn is not None:
                        if inspect.iscoroutinefunction(fn):
                            result = await fn(**kwargs)
                        else:
                            result = await asyncio.to_thread(fn, **kwargs)
                        return result if isinstance(result, str) else json.dumps(result)
                    return json.dumps(
                        {
                            "status": "ok",
                            "message": "Order received and confirmed.",
                            "order_id": "DRY-RUN-001",
                        }
                    )

                return _executor

            if tool_fn and (
                "item_details" in tool_name
                or "lookup" in tool_name
                or tool_name == "olo_create_order_v1"
            ):
                executors[tool_name] = _make_executor(tool_name, tool_fn)
            else:
                executors[tool_name] = _make_executor(tool_name, None)

    logger.info(
        "[REALTIME] Loaded %d pal-agent provider tool(s): %s",
        len(tools),
        [t["name"] for t in tools],
    )
    return tools, executors


def make_tool_executor(
    executors: dict,
) -> Callable[[str, str], Awaitable[str]]:
    """Create the dispatch function that routes tool calls to executors."""

    async def execute_tool(name: str, arguments: str) -> str:
        executor = executors.get(name)
        if not executor:
            return json.dumps({"error": f"Unknown tool: {name}"})
        args = json.loads(arguments) if arguments else {}
        if inspect.iscoroutinefunction(executor):
            result = await executor(**args)
        else:
            result = await asyncio.to_thread(executor, **args)
        return json.dumps(result) if not isinstance(result, str) else result

    return execute_tool
