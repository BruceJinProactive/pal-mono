import os


def get_server_url():
    runtime_env = os.getenv("RUNTIME_ENV")
    if runtime_env is None:
        raise ValueError("RUNTIME_ENV environment variable is not set")
    if runtime_env == "dev":
        return "http://localhost:8000"
    if runtime_env == "lat":
        return "https://lat-api.proactiveailab.com"
    elif runtime_env == "stg":
        return "https://stg-api.proactiveailab.com"
    elif runtime_env == "prd":
        return "https://api.proactiveailab.com"
    else:
        raise ValueError(f"Invalid runtime environment: {runtime_env}")
