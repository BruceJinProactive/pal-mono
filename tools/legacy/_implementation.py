from agno.tools.toolkit import Toolkit
from pydantic import BaseModel, Field, create_model

from agent.model import BaseOutputModel
from tools.escalation_tools import EscalationTools
from tools.legacy.booking_tools import BookingTools
from utils.log import logger


def get_tools(agent_raw_config, user_id, session_id):
    tools = []
    toolkit_map = {
        "BookingTools": BookingTools,
        "EscalationTools": EscalationTools,
    }

    if "tools" in agent_raw_config and type(agent_raw_config["tools"]) is list:
        for toolkit in agent_raw_config["tools"]:
            if (
                "toolkit" not in toolkit
                or "config" not in toolkit
                or type(toolkit["config"]) is not dict
            ):
                logger.warning("Toolkit in agent raw config is invalid.")
                logger.warning(toolkit)
                continue
            toolkit_name, toolkit_config = toolkit["toolkit"], toolkit["config"]

            tools.append(
                toolkit_map[toolkit_name](
                    toolkit_config, user_id=user_id, session_id=session_id
                )
            )

    return tools


def generate_output_model(tools: list[Toolkit]):
    class Empty(BaseModel):
        pass

    toolkit_field_map = {}

    OutputModel = create_model(
        "OutputModel",
        __config__=None,
        __doc__=None,
        __module__=__name__,
        __validators__=None,
        __cls_kwargs__=None,
        __base__=BaseOutputModel,
        # dynamically create fields for each toolkit
        **{
            key: (
                value.annotation,
                Field(..., description=value.description),
            )
            for t in tools
            for key, value in toolkit_field_map.get(t.name, Empty).model_fields.items()
        },
    )

    return OutputModel
