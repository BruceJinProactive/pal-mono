from os import getenv

# TODO: refactor dev_, stg_, and prd_resources.py to reduce duplicated code and just inject the parts that are different
common_container_env = {
    # Get LLM Hosting APIs key from the local environment
    "OPENAI_API_KEY": getenv("OPENAI_API_KEY"),
    "LEPTON_API_KEY": getenv("LEPTON_API_KEY"),
    "MODAL_API_KEY": getenv("MODAL_API_KEY"),
    # Get the SendBlue API key from the local environment
    "SENDBLUE_API_KEY": getenv("SENDBLUE_API_KEY"),
    "SENDBLUE_API_SECRET_KEY": getenv("SENDBLUE_API_SECRET_KEY"),
}
