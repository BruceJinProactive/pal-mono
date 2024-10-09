from . import _implementation


def get_tools(assistant_raw_config, user_id):
    """
    Initialize and return a list of toolkits based on the assistant raw configuration.

    Args:
        assistant_raw_config (dict): The raw configuration dictionary containing toolkit configurations.

    Returns:
        list: A list of initialized toolkit instances.

    Raises:
        KeyError: If the toolkit name is not found in the toolkit_map.
        TypeError: If the "tools" key is not a list or if the "config" key is not a dictionary.

    Example:
        assistant_raw_config = {
            "tools": [
                {
                    "toolkit": "OrderingTools",
                    "config": {"api_key": "your_api_key", "api_secret": "your_api_secret"}
                },
                {
                    "toolkit": "BookingTools",
                    "config": {"api_key": "another_api_key", "api_secret": "another_api_secret"}
                }
            ]
        }
        tools = get_tools(assistant_raw_config)
    """
    return _implementation.get_tools(assistant_raw_config, user_id)


__all__ = ["get_tools"]
