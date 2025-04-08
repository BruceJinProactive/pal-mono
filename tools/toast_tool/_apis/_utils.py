from tools.toast_tool.classes import ToastAccessToken, ToastHubResponse


def connect_toast_order_hub(
    http_method: str,
    bearer_token: ToastAccessToken,
    api_function: str,
    store_id: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    logging_enabled: bool = True,
) -> ToastHubResponse | None:
    pass
