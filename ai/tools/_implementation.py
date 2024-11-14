from utils.log import logger

from .booking_tools import BookingTools
from .escalation_tools import EscalationTools
from .image_retrieval_tools import ImageRetrievalTools
from .ordering_tools import OrderingTools


def get_tools(agent_raw_config, user_id):
    tools = []
    toolkit_map = {
        "OrderingTools": OrderingTools,
        "BookingTools": BookingTools,
        "EscalationTools": EscalationTools,
        "ImageRetrievalTools": ImageRetrievalTools,
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

            tools.append(toolkit_map[toolkit_name](toolkit_config, user_id))

    return tools
