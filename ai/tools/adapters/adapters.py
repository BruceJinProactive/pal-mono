from enum import Enum

from ai.tools.adapters.mock_cart import (
    add_mock_cart,
    checkout_mock_cart,
    get_mock_cart,
    remove_mock_cart,
    reset_mock_cart,
)


class ServiceAdapters(Enum):
    ADD_MOCK_CART = "ADD_MOCK_CART"
    REMOVE_MOCK_CART = "REMOVE_MOCK_CART"
    GET_MOCK_CART = "GET_MOCK_CART"
    CHECKOUT_MOCK_CART = "CHECKOUT_MOCK_CART"
    RESET_MOCK_CART = "RESET_MOCK_CART"


def get_adapter(adapter_name: ServiceAdapters):
    if adapter_name == ServiceAdapters.ADD_MOCK_CART:
        return add_mock_cart
    elif adapter_name == ServiceAdapters.REMOVE_MOCK_CART:
        return remove_mock_cart
    elif adapter_name == ServiceAdapters.GET_MOCK_CART:
        return get_mock_cart
    elif adapter_name == ServiceAdapters.CHECKOUT_MOCK_CART:
        return checkout_mock_cart
    elif adapter_name == ServiceAdapters.RESET_MOCK_CART:
        return reset_mock_cart
