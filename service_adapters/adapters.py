from enum import Enum

from service_adapters.mock_cart import add_mock_cart, get_mock_cart, order_mock_cart


class ServiceAdapters(Enum):
    ADD_MOCK_CART = "ADD_MOCK_CART"
    GET_MOCK_CART = "GET_MOCK_CART"
    ORDER_MOCK_CART = "ORDER_MOCK_CART"


def get_adapter(adapter_name: ServiceAdapters):
    if adapter_name == ServiceAdapters.ADD_MOCK_CART:
        return add_mock_cart
    elif adapter_name == ServiceAdapters.GET_MOCK_CART:
        return get_mock_cart
    elif adapter_name == ServiceAdapters.ORDER_MOCK_CART:
        return order_mock_cart
