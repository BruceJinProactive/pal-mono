"""
MenuSifu Tool classes
"""

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# Type alias for monetary values
Money = Decimal


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
    price: Money
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")


class Option(BaseModel):
    """Option for menu items or categories"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    price: Optional[Money] = None
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    max_num_of_item_option_allowed: Optional[int] = Field(
        None, alias="maxNumOfItemOptionAllowed"
    )
    sub_options: Optional[List[SubOption]] = Field(None, alias="subOptions")


class Tax(BaseModel):
    """Tax information"""

    model_config = ConfigDict(populate_by_name=True)

    tax_id: Optional[str] = Field(None, alias="_id")
    created_on: Optional[str] = Field(None, alias="createdOn")
    deleted: Optional[bool] = None
    id: Optional[int] = None
    last_updated: Optional[str] = Field(None, alias="lastUpdated")
    merchant_id: Optional[str] = Field(None, alias="merchantId")
    name: Optional[str] = None
    out_rate: Optional[Money] = Field(None, alias="outRate")
    price_limit: Optional[int] = Field(None, alias="priceLimit")
    rate: Optional[Money] = None
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
    price: Money
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
    price: Optional[Money] = None
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
    base_price: Optional[Money] = Field(None, alias="basePrice")
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

    model_config = ConfigDict(populate_by_name=True)


class Hours(BaseModel):
    """Menu group hours"""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: Optional[str] = None
    from_time: str = Field(alias="from")
    to_time: str = Field(alias="to")
    from_day_of_the_week: int = Field(alias="fromDayOfTheWeek")
    to_day_of_the_week: int = Field(alias="toDayOfTheWeek")


class MenuGroup(BaseModel):
    """Menu group containing categories"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: LocalizedName
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    description: Optional[str] = None
    categories: List[Category]
    hours: Optional[List[Hours]] = None


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
    id: Optional[int] = None  # Some options may not have ID (e.g. open options)
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    option_price: Optional[Money] = Field(None, alias="optionPrice")
    price: Money
    price_original: Optional[Money] = Field(None, alias="priceOriginal")
    quantity: int
    section_id: str = Field(alias="sectionId")
    section_name: Optional[MultilingualName] = Field(None, alias="sectionName")

    # Additional fields for new structure
    sub_options: Optional[List[Dict]] = Field(default_factory=list, alias="subOptions")
    sub_options_price: Optional[Money] = Field(None, alias="subOptionsPrice")
    is_open_option: Optional[bool] = Field(None, alias="isOpenOption")
    checked: Optional[bool] = None


class DetailPriceInfo(BaseModel):
    """Detail price information for order items"""

    model_config = ConfigDict(populate_by_name=True)

    detail_price_id: int = Field(alias="detailPriceId")
    size_id: int = Field(alias="sizeId")
    price: Money


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
    price: Money
    quantity: int
    sale_item_id: int = Field(alias="saleItemId")

    # Detail price fields for size variations
    detail_price_id: Optional[int] = Field(None, alias="detailPriceId")
    size_id: Optional[int] = Field(None, alias="sizeId")
    detail_price_info: Optional[DetailPriceInfo] = Field(None, alias="detailPriceInfo")


class OrderCalculationRequest(BaseModel):
    """Request body for order calculation API"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            Decimal: float,  # Serialize Decimals as numbers, not strings
            PaymentMethod: lambda v: v.value,  # Serialize PaymentMethod enum as numeric value
        },
    )

    delivery_fee: Money = Field(alias="deliveryFee")
    order_type: OrderType = Field(alias="orderType")
    payment_method: PaymentMethod = Field(alias="paymentMethod")
    selected_items: List[OrderSelectedItem] = Field(alias="selectedItems")
    total_tips: Money = Field(alias="totalTips")


class TaxDetail(BaseModel):
    """Tax detail for specific tax ID"""

    model_config = ConfigDict(populate_by_name=True)

    tax_amount: Money = Field(alias="taxAmount")


class OrderCalculationResponse(BaseModel):
    """Response from order calculation API"""

    model_config = ConfigDict(populate_by_name=True)

    order_subtotal: Money = Field(alias="orderSubtotal")
    order_promotion: Money = Field(alias="orderPromotion")
    order_discount: Money = Field(alias="orderDiscount")
    order_charge: Money = Field(alias="orderCharge")
    order_total_tips: Money = Field(alias="orderTotalTips")
    order_tax_detail: Dict[str, TaxDetail] = Field(alias="orderTaxDetail")
    order_tax_total: Money = Field(alias="orderTaxTotal")
    order_original_total: Money = Field(alias="orderOriginalTotal")
    rounding: Money
    order_total: Money = Field(alias="orderTotal")
    charge_obj: List["ChargeObjectInfo"] = Field(alias="chargeObj")
    online_fee: Money = Field(alias="onlineFee")
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
    price: Optional[Money] = None
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
    price: Money
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


# Order Generation API Classes


class Phone(BaseModel):
    """Phone number with country code"""

    model_config = ConfigDict(populate_by_name=True)

    country_code: str = Field(..., alias="countryCode", pattern=r"^\+\d{1,3}$")
    number: str = Field(..., min_length=5)


class Address(BaseModel):
    """Address information"""

    model_config = ConfigDict(populate_by_name=True)

    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = Field("", alias="zipCode")


class Customer(BaseModel):
    """Customer information"""

    model_config = ConfigDict(populate_by_name=True)

    email: str
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    phone: Phone
    address: Optional[Address] = None  # Optional address for responses that include it


class TaxInfo(BaseModel):
    """Tax information for order pricing"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={Decimal: float},  # Serialize Decimals as numbers, not strings
    )

    name: str
    value: Money
    rate: Money


class ChargeObjectInfo(BaseModel):
    """Charge object information for order pricing"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={Decimal: float},  # Serialize Decimals as numbers, not strings
    )

    charge: Money
    charge_is_per: Optional[bool] = Field(None, alias="chargeIsPer")
    charge_rate: Optional[Money] = Field(None, alias="chargeRate")
    type: Optional[str] = None


class OrderPrice(BaseModel):
    """Price information for order generation"""

    model_config = ConfigDict(
        populate_by_name=True,
        str_to_lower=False,
        json_encoders={Decimal: float},  # Serialize Decimals as numbers, not strings
    )

    subtotal: Money
    total: Money
    discount: Money = Decimal("0")
    online_fee: Money = Field(alias="onlineFee")
    delivery_fee: Money = Field(alias="deliveryFee")
    charge: Money
    charge_obj: List[ChargeObjectInfo] = Field(alias="chargeObj")
    tips: Money
    tax_total: Money = Field(alias="taxTotal")
    taxes: List[TaxInfo]
    charge_name: str = Field(alias="chargeName")
    discount_total_crm: Money = Field(Decimal("0"), alias="discountTotalCrm")
    rounding: Money = Decimal("0")


class DeliveryInfo(BaseModel):
    """Delivery information (empty for pickup orders)"""

    model_config = ConfigDict(populate_by_name=True)

    # Can add delivery-specific fields here if needed
    estimate_delivery_time: Optional[str] = Field(None, alias="estimateDeliveryTime")


class PointRule(BaseModel):
    """Point rule information for CRM"""

    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(alias="_id")
    last_updated_time: int = Field(alias="lastUpdatedTime")


class OrderItemOptionNote(BaseModel):
    """Option for order item (can be real option or note/comment)"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={Decimal: float},  # Serialize Decimals as numbers, not strings
    )

    # Section identification (for notes/custom options)
    section_id: Optional[str] = Field(None, alias="sectionId")
    section_name: Optional[MultilingualName] = Field(None, alias="sectionName")

    # For real options (condiments, etc.)
    id: Optional[int] = None
    detail_price_id: Optional[str] = Field(None, alias="detailPriceId")
    option_price: Optional[Money] = Field(None, alias="optionPrice")

    # For notes/comments and options
    name: Optional[str] = None
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    price: Money = Decimal("0")  # Should be 0 for notes
    price_original: Optional[Money] = Field(None, alias="priceOriginal")
    quantity: int = 1  # Should be 1 for notes
    checked: Optional[bool] = None  # Only for notes
    is_open_option: Optional[bool] = Field(None, alias="isOpenOption")  # Only for notes
    sub_options: Optional[List] = Field(
        default_factory=list, alias="subOptions"
    )  # Sub-options list


class OrderGenerationSelectedItem(BaseModel):
    """Selected item for order generation"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={Decimal: float},  # Serialize Decimals as numbers, not strings
    )

    id: int
    sale_item_id: int = Field(alias="saleItemId")
    quantity: int
    item_type: str = Field(alias="itemType")
    price: Money
    display_price: Optional[Money] = Field(
        None, alias="displayPrice"
    )  # item + partial prices per spec
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    category_id: int = Field(alias="categoryId")
    options: Optional[List[OrderItemOptionNote]] = None
    combo_detail: Optional["ComboDetail"] = Field(
        None, alias="comboDetail"
    )  # Forward reference


class OrderGenerationRequest(BaseModel):
    """Request for order generation API"""

    model_config = ConfigDict(
        populate_by_name=True,
        str_to_lower=False,
        json_encoders={
            Decimal: float,  # Serialize Decimals as numbers, not strings
            PaymentMethod: lambda v: v.value,  # Serialize PaymentMethod enum as numeric value
        },
    )

    # Required fields
    country_code: str = Field(alias="countryCode")
    telephone_number: str = Field(alias="telephoneNumber")
    channel: str = "WEB"  # Changed from "BOT" to match sample
    product_line: str = Field("ONLINE_ORDER", alias="productLine")
    order_type: OrderType = Field(alias="orderType")  # ONLINE_PICKUP, ONLINE_DELIVERY
    price: OrderPrice
    customer: Customer
    address: Address
    payment_method: PaymentMethod = Field(alias="paymentMethod")  # 1, 7, 8
    payment_info: str = Field("", alias="paymentInfo")
    pay_online: bool = Field(alias="payOnline")
    selected_items: List[OrderGenerationSelectedItem] = Field(alias="selectedItems")

    # Optional fields
    need_sms: Optional[bool] = Field(None, alias="needSms")
    riskified_id: Optional[str] = Field(None, alias="riskifiedId")
    online_type: str = Field("", alias="onlineType")
    delivery_info: dict = Field(default_factory=dict, alias="deliveryInfo")
    selected_gift_items: List = Field(default_factory=list, alias="selectedGiftItems")
    selected_gift_items_crm: List = Field(
        default_factory=list, alias="selectedGiftItemsCrm"
    )
    allergy_info: str = Field("", alias="allergyInfo")
    need_utensils: bool = Field(False, alias="needUtensils")
    need_straws: bool = Field(False, alias="needStraws")
    need_condiments: bool = Field(False, alias="needCondiments")
    mini_program: bool = Field(False, alias="miniProgram")
    business_id: Optional[str] = Field(None, alias="businessId")
    point_rule: Optional[PointRule] = Field(None, alias="pointRule")
    points: Optional[int] = None
    request_id: Optional[str] = Field(
        None, alias="_id"
    )  # For order updates, not used in BOT


# Response Models


class Timeline(BaseModel):
    """Timeline entry for order"""

    model_config = ConfigDict(populate_by_name=True)

    type: str
    time: int


class SelectSaleItem(BaseModel):
    """Selected sale item within a combo section"""

    model_config = ConfigDict(populate_by_name=True)

    sale_item_id: int = Field(alias="saleItemId")
    quantity: int
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    price: Money
    detail_price_id: str = Field(alias="detailPriceId")


class ComboSectionForOrder(BaseModel):
    """Combo section for order generation (different from menu combo section)"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    select_sale_items: List[SelectSaleItem] = Field(alias="selectSaleItems")


class ComboDetail(BaseModel):
    """Combo detail information for order generation"""

    model_config = ConfigDict(populate_by_name=True)

    combo_sections: List[ComboSectionForOrder] = Field(alias="comboSections")


class OrderItem(BaseModel):
    """Order item in the response"""

    model_config = ConfigDict(populate_by_name=True)

    choice_labels: List[str] = Field(default_factory=list, alias="choiceLabels")
    combo_detail: Optional[ComboDetail] = Field(None, alias="comboDetail")
    sale_item_id: int = Field(alias="saleItemId")
    quantity: int
    item_type: str = Field(alias="itemType")
    price: Money
    display_price: Money = Field(alias="displayPrice")
    name: str
    name_multilingual: Optional[MultilingualName] = Field(
        None, alias="nameMultilingual"
    )
    category_id: int = Field(alias="categoryId")
    options: Optional[List[OrderItemOptionNote]] = Field(default_factory=list)


class SelectedPaymentInfo(BaseModel):
    """Selected payment information"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            Decimal: float,  # Serialize Decimals as numbers, not strings
            PaymentMethod: lambda v: v.value,  # Serialize PaymentMethod enum as numeric value
        },
    )

    pay_online: bool = Field(alias="payOnline")
    payment_method: PaymentMethod = Field(alias="paymentMethod")


class PrepareTime(BaseModel):
    """Preparation time range"""

    model_config = ConfigDict(populate_by_name=True)

    min: int
    max: int


class Contains(BaseModel):
    """Order contents information"""

    model_config = ConfigDict(populate_by_name=True)

    alcohol: bool = False


class OrderDiscount(BaseModel):
    """Order discount information"""

    model_config = ConfigDict(populate_by_name=True)

    # Add discount fields as needed
    pass


class OrderCharge(BaseModel):
    """Order charge information"""

    model_config = ConfigDict(populate_by_name=True)

    charge: Money
    charge_name: str = Field(alias="chargeName")


class PosTax(BaseModel):
    """POS tax information"""

    model_config = ConfigDict(populate_by_name=True)

    tax_amount: Money = Field(alias="taxAmount")
    tax: Dict[str, int]  # Contains "id" field


class OrderResponsePrice(BaseModel):
    """Price information in order response"""

    model_config = ConfigDict(populate_by_name=True)

    subtotal: Money
    total: Money
    discount: Money
    online_fee: Money = Field(alias="onlineFee")
    delivery_fee: Money = Field(alias="deliveryFee")
    charge: Money
    charge_obj: List[ChargeObjectInfo] = Field(alias="chargeObj")
    tips: Money
    tax_total: Money = Field(alias="taxTotal")
    taxes: List[TaxInfo]
    charge_name: str = Field(alias="chargeName")
    rounding: Money
    order_discounts: List[OrderDiscount] = Field(
        default_factory=list, alias="orderDiscounts"
    )
    discount_name: str = Field("", alias="discountName")
    rounding_amount: Money = Field(alias="roundingAmount")
    order_charges: List[OrderCharge] = Field(default_factory=list, alias="orderCharges")
    pos_taxes: List[PosTax] = Field(default_factory=list, alias="posTaxes")


class Order(BaseModel):
    """Order information in response - simplified to match actual API response"""

    model_config = ConfigDict(
        populate_by_name=True, extra="allow"
    )  # Allow extra fields

    # Core fields present in actual API response
    _id: Optional[str] = None
    type: Optional[str] = None  # Changed from OrderType to str for flexibility
    productLine: Optional[str] = None
    status: Optional[int] = None
    orderNumber: Optional[str] = None
    orderItems: Optional[List[Dict]] = Field(default_factory=list)  # Simplified as Dict
    price: Optional[Dict] = None  # Keep as Dict to avoid validation issues


class OrderGenerationResponse(BaseModel):
    """Response from order generation API"""

    model_config = ConfigDict(populate_by_name=True, str_to_lower=False)

    payment_url: Optional[str] = Field(None, alias="paymentUrl")
    payment_html: str = Field("", alias="paymentHtml")
    order: Order
    successful: bool = (
        True  # Default to True since we only get here on successful API calls
    )


# ===== EXTRACTION CLASSES FOR LLM OUTPUT =====
# These classes are specifically for LLM extraction output
# and are more flexible than the API request/response classes


class ExtractedMenuSifuModifier(BaseModel):
    """Extracted modifier/option from chat history"""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    name: str
    price: Optional[float] = None
    quantity: int = 1
    checked: bool = True


class ExtractedMenuSifuItem(BaseModel):
    """Extracted menu item from chat history with MenuSifu-specific fields"""

    model_config = ConfigDict(populate_by_name=True)

    item_name: str
    item_id: Optional[str] = None
    sale_item_id: Optional[str] = None
    quantity: int = 1
    price: Optional[float] = None
    display_price: Optional[float] = None
    item_type: str = "SALE_ITEM"
    category_id: Optional[int] = None
    special_notes: Optional[str] = None
    modifiers: List[ExtractedMenuSifuModifier] = Field(default_factory=list)


class ExtractedMenuSifuOrder(BaseModel):
    """Extracted complete order from chat history with MenuSifu-specific fields"""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={
            Decimal: float,  # Serialize Decimals as numbers, not strings
            PaymentMethod: lambda v: v.value,  # Serialize PaymentMethod enum as numeric value
        },
    )

    # Customer information (must be provided in chat for order processing)
    email: Optional[str] = None
    firstName: str = Field(..., min_length=1)
    lastName: Optional[str] = None
    phone: Phone  # Required field - not Optional

    # Required fields
    items: List[ExtractedMenuSifuItem]

    # Order configuration
    order_type: OrderType = OrderType.ONLINE_PICKUP
    payment_method: PaymentMethod = PaymentMethod.CASH

    # Delivery address (only for ONLINE_DELIVERY) - reuse existing Address class
    delivery_address: Optional[Address] = None

    # Additional notes and dietary information
    special_instructions: Optional[str] = None
    allergy_info: Optional[str] = None
    need_utensils: Optional[bool] = None
    need_straws: Optional[bool] = None
    need_condiments: Optional[bool] = None
