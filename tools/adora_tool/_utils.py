from typing import Any, Optional, Tuple, TypeVar

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm, task
from geopy.geocoders import Nominatim
from pydantic import BaseModel

from tools.adora_tool.classes import DeliveryAddress
from utils.log import logger

EXTRACTOR_SYSTEM_PROMPT = """You are an expert at structured data extraction.
You will be given the chat history and relevant context.
You goal is to convert it into the given structure.

**Instructions on how to perform the task:**
First, identify if the user wants to order for delivery or pickup.
If it's delivery, identify the delivery address. If it's pickup, leave the
address field empty.
Then, identify the list of items that the user wants to order from the chat history.
Then, make sure that the quantities for each order are correct.
Then, make sure that the modifiers for every order are identified, if they were mentioned in the chat history.
Finally, map the items, names, modifiers, etc., that you just identified from the english language to the structured data format that is required by the Adora API using the provided context.
Importantly, some of the provided context might be irrelevant to the order,
in which case you should ignore it.

**RULES FOR EXTRACTING THE DELIRERY ADDRESS:**
- Extract the last delivery address from the context.
- For the state field, if the user provides an abbreviation, output the full state name, i.e., if the user entered "CA", output "California".
- If any field is missing, output "N/A" for that field, i.e., if the user did not
provide a delivery address, output "N/A" for all fields.

**RULES FOR EXTRACTING THE ORDER ITEMS:**
- Extract the last order items from the context.
- The original item ingredients are not considered as modifiers.
- Only include modifiers that were explicitly mentioned by the user in the chat history.


**IMPORTANT RULES:**
- Do NOT make assumptions or fabricate data
- Leave fields as None/null if the information is not explicitly mentioned
- Do not infer values or make educated guesses
- Only extract information that is directly stated
- Maintain exact values as mentioned (don't modify numbers or text)
- For phone numbers, only extract if a complete number is provided
- For addresses, only extract if all required components are present

If unsure about any field, leave it empty rather than guessing."
"""

EXTRACTOR_USER_PROMPT = """
Please construct the structured order from the following information:

**Menu items with the corresponding modifiers**
{context}

**Chat History**
{chat_history}
"""

T = TypeVar("T", bound=BaseModel)


@llm(name="extractor")
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name="tool",
    reasoning=True,
) -> Optional[T]:
    # client = get_model(model_name=ModelName.MEDIUM)
    model_name = (
        "deepseek-r1-distill-llama-70b" if reasoning else "llama-3.3-70b-versatile"
    )
    client = Groq(id=model_name)

    if response_format:
        system_prompt += """
        \n
        Structure your response as a dictionary, do not include "json" in the beginning
        of the response.
        """

    # Deepseek models works better if everything is passed in the user prompt
    if "deepseek" in model_name:
        prompt = "\n\n".join([system_prompt, prompt])
        system_prompt = ""

    agent = Agent(
        model=client,
        agent_id=f"ordering-tools/{name}",
        session_id="test-session",
        add_history_to_messages=True,
        knowledge=None,
        debug_mode=True,
        response_model=response_format,
        system_message=system_prompt,
        num_history_responses=0,
        search_knowledge=False,
    )

    response = agent.run(prompt).content

    LLMObs.annotate(
        input_data=prompt,
        output_data=response,
        metadata={"system_prompt": system_prompt},
    )

    return response


@task
def add_lat_long_to_address(delivery_address: DeliveryAddress) -> Tuple[bool, str]:
    """
    Add latitude and longitude to a delivery address. Modifies the delivery address
    object in place.

    Args:
        delivery_address (DeliveryAddress): The delivery address to add latitude and
        longitude to.

    Returns:
        Tuple[bool, str]: A tuple containing a boolean indicating whether the latitude
        and longitude were added successfully, and a string message summarizing the
        result.
    """
    if delivery_address.address == "N/A" or delivery_address.city == "N/A":
        return (
            False,
            "Ask the user to provide at least a street address and city.",
        )

    # setup Nominatim to convert address to lat long coordinates
    # TODO: Usage limited to 1qps without API key. Upgrade to paid plan when needed.
    # TODO: https://aws.amazon.com/location/
    geolocator = Nominatim(user_agent="pal")

    geo_payload = {
        "street": delivery_address.address,
        "city": delivery_address.city,
        "state": (delivery_address.state if delivery_address.state != "N/A" else ""),
        "country": "USA",
        "postalcode": (delivery_address.zip if delivery_address.zip != "N/A" else ""),
    }
    logger.debug(
        "[AdoraTool.add_lat_long_to_address] Geolocator payload: " + str(geo_payload)
    )
    geocoded_loc: Any = geolocator.geocode(geo_payload)
    logger.debug(
        f"[AdoraTool.add_lat_long_to_address] Geocoded location: {bool(geocoded_loc)}"
    )
    if not geocoded_loc:
        logger.debug("[AdoraTool.add_lat_long_to_address] Failed to geocode address.")
        return (
            False,
            "The address that the user provided is invalid. Please provide a valid address. "
            + (
                "Try providing a state and zipcode."
                if delivery_address.state == "N/A" or delivery_address.zip == "N/A"
                else ""
            ),
        )

    logger.debug(
        "[AdoraTool.add_lat_long_to_address] Nominatim API result: "
        + str(geocoded_loc.latitude)
        + ", "
        + str(geocoded_loc.longitude)
    )

    # auto-populate state and zipcode
    if delivery_address.state == "N/A" or delivery_address.zip == "N/A":
        return (
            False,
            "Please provide your full address with zip code and state information.",
        )

    if (
        not delivery_address
        or delivery_address.address == "N/A"
        or delivery_address.city == "N/A"
        or delivery_address.state == "N/A"
        or delivery_address.zip == "N/A"
    ):
        logger.debug(
            f"[AdoraTool.add_lat_long_to_address] Failed to convert address. Delivery address object: {delivery_address}"
        )
        return (
            False,
            "Something went wrong with delivery address conversion. Please try again.",
        )
    delivery_address.lat = geocoded_loc.latitude
    delivery_address.lng = geocoded_loc.longitude
    return (True, "Latitude and longitude added to delivery address.")
