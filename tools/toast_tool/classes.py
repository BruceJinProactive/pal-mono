from pydantic import BaseModel


class ToastHubResponse(BaseModel):
    pass


class ToastAccessToken(BaseModel):
    """
    This class represents the response from the Toast Authentication API.
    It contains the access token used to authenticate subsequent API calls.

    Based on the Toast API documentation, this token is obtained by sending a POST request to:
    https://[toast-api-hostname]/authentication/v1/authentication/login
    """

    pass


class Order(BaseModel):
    pass
