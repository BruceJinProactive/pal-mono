"""
MenuSifu Tool classes
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class LocalizedName(BaseModel):
    """Localized name with English and Chinese"""

    model_config = ConfigDict(populate_by_name=True)

    en: Optional[str] = None
    zh_cn: Optional[str] = Field(None, alias="zh-cn")


class SubOption(BaseModel):
    """Sub-option within an option"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    price: Union[int, float]
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")


class Option(BaseModel):
    """Option for menu items or categories"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    price: Optional[Union[int, float]] = None
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    max_num_of_item_option_allowed: Optional[int] = Field(
        None, alias="maxNumOfItemOptionAllowed"
    )
    sub_options: Optional[List[SubOption]] = Field(None, alias="subOptions")


class Tax(BaseModel):
    """Tax information"""

    model_config = ConfigDict(populate_by_name=True)

    _id: Optional[str] = None
    created_on: Optional[str] = Field(None, alias="createdOn")
    deleted: Optional[bool] = None
    id: Optional[int] = None
    last_updated: Optional[str] = Field(None, alias="lastUpdated")
    merchant_id: Optional[str] = Field(None, alias="merchantId")
    name: Optional[str] = None
    out_rate: Optional[Union[int, float]] = Field(None, alias="outRate")
    price_limit: Optional[int] = Field(None, alias="priceLimit")
    rate: Optional[Union[int, float]] = None
    system_generated: Optional[bool] = Field(None, alias="systemGenerated")
    tax_increase: Optional[str] = Field(None, alias="taxIncrease")
    tax_increase_rate: Optional[int] = Field(None, alias="taxIncreaseRate")


class Property(BaseModel):
    """Item property"""

    model_config = ConfigDict(populate_by_name=True)

    display_name: Optional[str] = Field(None, alias="displayName")
    name: Optional[str] = None
    value: Optional[bool] = None


class Size(BaseModel):
    """Size information for detailed pricing"""

    model_config = ConfigDict(populate_by_name=True)

    en: Optional[str] = None
    zh_cn: Optional[str] = Field(None, alias="zh-cn")


class Price(BaseModel):
    """Price information with size and order type"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    order_type: str = Field(alias="orderType")
    price: Union[int, float]
    size: Size
    size_id: int = Field(alias="sizeId")


class DetailPrice(BaseModel):
    """Detailed pricing information with different sizes"""

    prices: List[Price]


class ComboSectionSaleItem(BaseModel):
    """Sale item within a combo section"""

    model_config = ConfigDict(populate_by_name=True)

    pre_selected: bool = Field(alias="preSelected")
    sale_item_id: int = Field(alias="saleItemId")


class ComboSection(BaseModel):
    """Combo section information"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    allow_repeated_items: Optional[bool] = Field(None, alias="allowRepeatedItems")
    combo_section_sale_items: List[ComboSectionSaleItem] = Field(
        alias="comboSectionSaleItems"
    )
    item_selection_rule: int = Field(alias="itemSelectionRule")
    max_num_of_selection_allowed: Optional[int] = Field(
        None, alias="maxNumOfSelectionAllowed"
    )
    min_num_of_selection_allowed: Optional[int] = Field(
        None, alias="minNumOfSelectionAllowed"
    )
    price_rule: int = Field(alias="priceRule")


class SaleItem(BaseModel):
    """Menu sale item"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    item_type: str = Field(alias="itemType")
    price: Optional[Union[int, float]] = None
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    item_number: Optional[str] = Field(None, alias="itemNumber")
    hidden_item: Optional[bool] = Field(None, alias="hiddenItem")
    out_of_stock: Optional[bool] = Field(None, alias="outOfStock")
    thumb_path: Optional[Any] = Field(None, alias="thumbPath")
    default_item_size_id: Optional[int] = Field(None, alias="defaultItemSizeId")
    max_num_of_item_option_allowed: Optional[int] = Field(
        None, alias="maxNumOfItemOptionAllowed"
    )

    # Combo-specific fields
    combo_type: Optional[int] = Field(None, alias="comboType")
    base_price: Optional[Union[int, float]] = Field(None, alias="basePrice")
    combo_sections: Optional[List[ComboSection]] = Field(None, alias="comboSections")

    # Additional fields
    detail_price: Optional[DetailPrice] = Field(None, alias="detailPrice")
    options: Optional[List[Option]] = None
    properties: Optional[List[Property]] = None


class Category(BaseModel):
    """Menu category"""

    id: int
    name: LocalizedName
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    description: Optional[str] = None
    hidden_category: Optional[bool] = Field(None, alias="hiddenCategory")
    require_category: Optional[bool] = Field(None, alias="requireCategory")
    applicable_to_order_discount: Optional[bool] = Field(
        None, alias="applicableToOrderDiscount"
    )
    discount_allowed: Optional[bool] = Field(None, alias="discountAllowed")
    do_not_display_for_emenu_and_cravee: Optional[bool] = Field(
        None, alias="doNotDisplayForEMenuAndCravee"
    )
    qty_qualifying_for_zero_rated: Optional[int] = Field(
        None, alias="qtyQualifyingForZeroRated"
    )

    sale_items: List[SaleItem] = Field(alias="saleItems")
    options: Optional[List[Option]] = None
    taxes: Optional[List[Tax]] = None

    class Config:
        allow_population_by_field_name = True


class Hours(BaseModel):
    """Menu group hours"""

    name: str
    description: Optional[str] = None
    from_time: str = Field(alias="from")
    to_time: str = Field(alias="to")
    from_day_of_the_week: int = Field(alias="fromDayOfTheWeek")
    to_day_of_the_week: int = Field(alias="toDayOfTheWeek")

    class Config:
        allow_population_by_field_name = True


class MenuGroup(BaseModel):
    """Menu group containing categories"""

    id: int
    name: LocalizedName
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    description: Optional[str] = None
    categories: List[Category]
    hours: Optional[List[Hours]] = None

    class Config:
        allow_population_by_field_name = True


class MenuResponse(BaseModel):
    """Complete menu response from MenuSifu API"""

    id: int
    name: LocalizedName
    successful: bool
    groups: List[MenuGroup]


# Order Calculation API Classes


class OrderType(str, Enum):
    """Order type enumeration"""

    ONLINE_DELIVERY = "ONLINE_DELIVERY"
    ONLINE_PICKUP = "ONLINE_PICKUP"


class PaymentMethod(int, Enum):
    """Payment method enumeration"""

    CREDIT_CARD = 1
    ACCOUNT = 2
    LOYALTY_CARD = 3
    GIFT_CARD = 4
    DEBIT_CARD = 5
    UNKNOWN = 6
    CASH = 7
    WECHAT_PAY = 8
    ALI_PAY = 9
    ONLINE = 10
    MOBILE = 11
    PAYPAL = 200
    APPLE_PAY = 300
    GOOGLE_PAY = 301


class ErrorType(str, Enum):
    """Error type enumeration for order validation"""

    OPTION_DELETED = "OPTION_DELETED"
    CLOSING = "CLOSING"
    NOT_FOUND = "NOT_FOUND"
    SOLD_OUT = "SOLD_OUT"
    DELETED = "DELETED"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OPTION_LIMIT = "OPTION_LIMIT"


class MultilingualName(BaseModel):
    """Extended multilingual name supporting multiple languages"""

    model_config = ConfigDict(populate_by_name=True)

    en: Optional[str] = None
    zh_cn: Optional[str] = Field(None, alias="zh-cn")
    french: Optional[str] = Field(None, alias="French")
    es: Optional[str] = None


class OrderItemOption(BaseModel):
    """Option for an order item"""

    model_config = ConfigDict(populate_by_name=True)

    detail_price_id: Optional[str] = Field(None, alias="detailPriceId")
    id: int
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    option_price: Union[int, float] = Field(alias="optionPrice")
    price: Union[int, float]
    price_original: Union[int, float] = Field(alias="priceOriginal")
    quantity: int
    section_id: str = Field(alias="sectionId")
    section_name: MultilingualName = Field(alias="sectionName")


class DetailPriceInfo(BaseModel):
    """Detail price information for order items"""

    model_config = ConfigDict(populate_by_name=True)

    detail_price_id: int = Field(alias="detailPriceId")
    size_id: int = Field(alias="sizeId")
    price: Union[int, float]


class OrderSelectedItem(BaseModel):
    """Selected item in the order"""

    model_config = ConfigDict(populate_by_name=True)

    category_id: int = Field(alias="categoryId")
    display_price: Optional[int] = Field(
        None, alias="displayPrice"
    )  # Optional, not used
    id: int
    item_type: str = Field(alias="itemType")
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    options: Optional[List[OrderItemOption]] = None
    price: Union[int, float]
    quantity: int
    sale_item_id: int = Field(alias="saleItemId")

    # Detail price fields for size variations
    detail_price_id: Optional[int] = Field(None, alias="detailPriceId")
    size_id: Optional[int] = Field(None, alias="sizeId")
    detail_price_info: Optional[DetailPriceInfo] = Field(None, alias="detailPriceInfo")


class OrderCalculationRequest(BaseModel):
    """Request body for order calculation API"""

    model_config = ConfigDict(populate_by_name=True)

    delivery_fee: float = Field(alias="deliveryFee")
    order_type: OrderType = Field(alias="orderType")
    payment_method: PaymentMethod = Field(alias="paymentMethod")
    selected_items: List[OrderSelectedItem] = Field(alias="selectedItems")
    total_tips: float = Field(alias="totalTips")


class TaxDetail(BaseModel):
    """Tax detail for specific tax ID"""

    model_config = ConfigDict(populate_by_name=True)

    tax_amount: Union[int, float] = Field(alias="taxAmount")


class ChargeObject(BaseModel):
    """Charge object information"""

    model_config = ConfigDict(populate_by_name=True)

    charge: Union[int, float]
    charge_is_per: bool = Field(alias="chargeIsPer")
    charge_rate: Union[int, float] = Field(alias="chargeRate")
    type: str


class OrderCalculationResponse(BaseModel):
    """Response from order calculation API"""

    model_config = ConfigDict(populate_by_name=True)

    order_subtotal: Union[int, float] = Field(alias="orderSubtotal")
    order_promotion: Union[int, float] = Field(alias="orderPromotion")
    order_discount: Union[int, float] = Field(alias="orderDiscount")
    order_charge: Union[int, float] = Field(alias="orderCharge")
    order_total_tips: Union[int, float] = Field(alias="orderTotalTips")
    order_tax_detail: Dict[str, TaxDetail] = Field(alias="orderTaxDetail")
    order_tax_total: Union[int, float] = Field(alias="orderTaxTotal")
    order_original_total: Union[int, float] = Field(alias="orderOriginalTotal")
    rounding: Union[int, float]
    order_total: Union[int, float] = Field(alias="orderTotal")
    charge_obj: List[ChargeObject] = Field(alias="chargeObj")
    online_fee: Union[int, float] = Field(alias="onlineFee")
    charge_name: str = Field(alias="chargeName")
    successful: bool


# Error Response Classes


class ErrorData(BaseModel):
    """Base error data"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    deleted: Optional[bool] = None
    name: Optional[str] = None


class DetailedErrorData(ErrorData):
    """Detailed error data with full item information"""

    detail_prices: Optional[List[DetailPrice]] = Field(None, alias="detailPrices")
    hidden_item: Optional[bool] = Field(None, alias="hiddenItem")
    item_type: Optional[str] = Field(None, alias="itemType")
    out_of_stock: Optional[bool] = Field(None, alias="outOfStock")
    price: Optional[Union[int, float]] = None
    printer_ids: Optional[List[int]] = Field(None, alias="printerIds")
    properties: Optional[List[Property]] = None
    taxes: Optional[List[Tax]] = None
    category_id: Optional[int] = Field(None, alias="categoryId")
    group_id: Optional[int] = Field(None, alias="groupId")
    group_hours: Optional[List[Hours]] = Field(None, alias="groupHours")


class OptionDeletedErrorData(BaseModel):
    """Error data for deleted option"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    deleted: bool
    name: str
    price: Union[int, float]
    option_type: str = Field(alias="optionType")


class SoldOutErrorData(BaseModel):
    """Error data for sold out items"""

    model_config = ConfigDict(populate_by_name=True)

    merchant_id: str = Field(alias="merchantId")
    id: int
    name: str


class ErrorMessage(BaseModel):
    """Error message structure"""

    model_config = ConfigDict(populate_by_name=True)

    type: ErrorType
    error: str
    data: Union[DetailedErrorData, OptionDeletedErrorData, SoldOutErrorData, ErrorData]


class OrderCalculationErrorResponse(BaseModel):
    """Error response from order calculation API"""

    model_config = ConfigDict(populate_by_name=True)

    message: ErrorMessage
    id: Optional[int] = None
    successful: bool
