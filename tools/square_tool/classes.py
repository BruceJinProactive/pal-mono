from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class CatalogObjectType(str, Enum):
    """Enum for catalog object types"""

    ITEM = "ITEM"
    IMAGE = "IMAGE"
    CATEGORY = "CATEGORY"
    ITEM_VARIATION = "ITEM_VARIATION"
    TAX = "TAX"
    DISCOUNT = "DISCOUNT"
    MODIFIER_LIST = "MODIFIER_LIST"
    MODIFIER = "MODIFIER"
    PRICING_RULE = "PRICING_RULE"
    PRODUCT_SET = "PRODUCT_SET"
    TIME_PERIOD = "TIME_PERIOD"
    MEASUREMENT_UNIT = "MEASUREMENT_UNIT"
    SUBSCRIPTION_PLAN_VARIATION = "SUBSCRIPTION_PLAN_VARIATION"
    ITEM_OPTION = "ITEM_OPTION"
    ITEM_OPTION_VAL = "ITEM_OPTION_VAL"
    CUSTOM_ATTRIBUTE_DEFINITION = "CUSTOM_ATTRIBUTE_DEFINITION"
    QUICK_AMOUNTS_SETTINGS = "QUICK_AMOUNTS_SETTINGS"
    SUBSCRIPTION_PLAN = "SUBSCRIPTION_PLAN"
    AVAILABILITY_PERIOD = "AVAILABILITY_PERIOD"


class Money(BaseModel):
    """Represents a monetary amount with currency"""

    amount: int
    currency: str


class CatalogV1Id(BaseModel):
    """Connect v1 IDs for backward compatibility"""

    catalog_v1_id: Optional[str] = None
    location_id: Optional[str] = None


class CatalogCustomAttributeValue(BaseModel):
    """Custom attribute value"""

    name: Optional[str] = None
    string_value: Optional[str] = None
    custom_attribute_definition_id: Optional[str] = None
    type: Optional[str] = None
    number_value: Optional[str] = None
    boolean_value: Optional[bool] = None
    selection_uid_values: Optional[List[str]] = None
    key: Optional[str] = None


class CategoryPathToRootNode(BaseModel):
    """Path node for category hierarchy"""

    category_id: Optional[str] = None
    category_name: Optional[str] = None


class CatalogObjectCategory(BaseModel):
    """Reference to a catalog category"""

    id: Optional[str] = None
    ordinal: Optional[int] = None


class ItemVariationLocationOverrides(BaseModel):
    """Location-specific overrides for item variations"""

    location_id: Optional[str] = None
    price_money: Optional[Money] = None
    pricing_type: Optional[str] = None
    track_inventory: Optional[bool] = None
    inventory_alert_type: Optional[str] = None
    inventory_alert_threshold: Optional[int] = None
    sold_out: Optional[bool] = None
    sold_out_valid_until: Optional[str] = None


class CatalogItemOptionValueForItemVariation(BaseModel):
    """Item option value for item variation"""

    item_option_id: Optional[str] = None
    item_option_value_id: Optional[str] = None


class CatalogStockConversion(BaseModel):
    """Stock conversion data"""

    stockable_item_variation_id: str
    stockable_quantity: str
    nonstockable_quantity: str


class CatalogItemVariation(BaseModel):
    """Data for a catalog item variation"""

    item_id: Optional[str] = None
    name: Optional[str] = None
    sku: Optional[str] = None
    upc: Optional[str] = None
    ordinal: Optional[int] = None
    pricing_type: Optional[str] = None
    price_money: Optional[Money] = None
    location_overrides: Optional[List[ItemVariationLocationOverrides]] = None
    track_inventory: Optional[bool] = None
    inventory_alert_type: Optional[str] = None
    inventory_alert_threshold: Optional[int] = None
    user_data: Optional[str] = None
    service_duration: Optional[int] = None
    available_for_booking: Optional[bool] = None
    item_option_values: Optional[List[CatalogItemOptionValueForItemVariation]] = None
    measurement_unit_id: Optional[str] = None
    sellable: Optional[bool] = None
    stockable: Optional[bool] = None
    image_ids: Optional[List[str]] = None
    team_member_ids: Optional[List[str]] = None
    stockable_conversion: Optional[CatalogStockConversion] = None


class CatalogItemModifierListInfo(BaseModel):
    """Modifier list info for items"""

    modifier_list_id: str
    modifier_overrides: Optional[List[Any]] = None
    min_selected_modifiers: Optional[int] = None
    max_selected_modifiers: Optional[int] = None
    enabled: Optional[bool] = None
    ordinal: Optional[int] = None


class CatalogItemOptionForItem(BaseModel):
    """Item option for item"""

    item_option_id: Optional[str] = None


class CatalogEcomSeoData(BaseModel):
    """SEO data for e-commerce"""

    page_title: Optional[str] = None
    page_description: Optional[str] = None
    permalink: Optional[str] = None


class CatalogItemFoodAndBeverageDetails(BaseModel):
    """Food and beverage specific details"""

    calorie_count: Optional[int] = None
    dietary_preferences: Optional[List[str]] = None
    ingredients: Optional[List[Any]] = None


class CatalogItem(BaseModel):
    """Data for a catalog item"""

    name: Optional[str] = None
    description: Optional[str] = None
    abbreviation: Optional[str] = None
    label_color: Optional[str] = None
    is_taxable: Optional[bool] = None
    category_id: Optional[str] = None
    tax_ids: Optional[List[str]] = None
    modifier_list_info: Optional[List[CatalogItemModifierListInfo]] = None
    variations: Optional[List["CatalogItemVariationObject"]] = None
    product_type: Optional[str] = None
    skip_modifier_screen: Optional[bool] = None
    item_options: Optional[List[CatalogItemOptionForItem]] = None
    ecom_uri: Optional[str] = None
    ecom_image_uris: Optional[List[str]] = None
    image_ids: Optional[List[str]] = None
    sort_name: Optional[str] = None
    categories: Optional[List[CatalogObjectCategory]] = None
    description_html: Optional[str] = None
    description_plaintext: Optional[str] = None
    channels: Optional[List[str]] = None
    is_archived: Optional[bool] = None
    ecom_seo_data: Optional[CatalogEcomSeoData] = None
    food_and_beverage_details: Optional[CatalogItemFoodAndBeverageDetails] = None
    reporting_category: Optional[CatalogObjectCategory] = None
    is_alcoholic: Optional[bool] = None


class CatalogCategory(BaseModel):
    """Data for a catalog category"""

    name: Optional[str] = None
    image_ids: Optional[List[str]] = None
    category_type: Optional[str] = None
    parent_category: Optional[CatalogObjectCategory] = None
    is_top_level: Optional[bool] = None
    channels: Optional[List[str]] = None
    availability_period_ids: Optional[List[str]] = None
    online_visibility: Optional[bool] = None
    root_category: Optional[str] = None
    ecom_seo_data: Optional[CatalogEcomSeoData] = None
    path_to_root: Optional[List[CategoryPathToRootNode]] = None


class ModifierLocationOverrides(BaseModel):
    """Location overrides for modifiers"""

    location_id: Optional[str] = None
    price_money: Optional[Money] = None


class CatalogModifier(BaseModel):
    """Data for a catalog modifier"""

    name: Optional[str] = None
    price_money: Optional[Money] = None
    on_by_default: Optional[bool] = None
    ordinal: Optional[int] = None
    modifier_list_id: Optional[str] = None
    location_overrides: Optional[List[ModifierLocationOverrides]] = None
    image_id: Optional[str] = None
    hidden_online: Optional[bool] = None


class CatalogModifierList(BaseModel):
    """Data for a catalog modifier list"""

    name: Optional[str] = None
    ordinal: Optional[int] = None
    selection_type: Optional[str] = None
    modifiers: Optional[List["CatalogModifierObject"]] = None
    image_ids: Optional[List[str]] = None
    allow_quantities: Optional[bool] = None
    is_conversational: Optional[bool] = None
    modifier_type: Optional[str] = None
    max_length: Optional[int] = None
    text_required: Optional[bool] = None
    internal_name: Optional[str] = None
    min_selected_modifiers: Optional[int] = None
    max_selected_modifiers: Optional[int] = None
    hidden_from_customer: Optional[bool] = None


class CatalogTax(BaseModel):
    """Data for a catalog tax"""

    name: Optional[str] = None
    calculation_phase: Optional[str] = None
    inclusion_type: Optional[str] = None
    percentage: Optional[str] = None
    applies_to_custom_amounts: Optional[bool] = None
    enabled: Optional[bool] = None
    applies_to_product_set_id: Optional[str] = None


class CatalogDiscount(BaseModel):
    """Data for a catalog discount"""

    name: Optional[str] = None
    discount_type: Optional[str] = None
    percentage: Optional[str] = None
    amount_money: Optional[Money] = None
    pin_required: Optional[bool] = None
    label_color: Optional[str] = None
    modify_tax_basis: Optional[str] = None
    maximum_amount_money: Optional[Money] = None


class CatalogImage(BaseModel):
    """Data for a catalog image"""

    name: Optional[str] = None
    url: Optional[str] = None
    caption: Optional[str] = None
    photo_studio_order_id: Optional[str] = None


class MeasurementUnit(BaseModel):
    """Measurement unit details"""

    custom_unit: Optional[Any] = None
    area_unit: Optional[str] = None
    length_unit: Optional[str] = None
    volume_unit: Optional[str] = None
    weight_unit: Optional[str] = None
    generic_unit: Optional[str] = None
    time_unit: Optional[str] = None
    type: Optional[str] = None


class CatalogMeasurementUnit(BaseModel):
    """Data for a catalog measurement unit"""

    measurement_unit: Optional[MeasurementUnit] = None
    precision: Optional[int] = None


class CatalogItemOption(BaseModel):
    """Data for a catalog item option"""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    show_colors: Optional[bool] = None
    values: Optional[List["CatalogItemOptionValueObject"]] = None


class CatalogItemOptionValue(BaseModel):
    """Data for a catalog item option value"""

    item_option_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    ordinal: Optional[int] = None


class SourceApplication(BaseModel):
    """Source application info"""

    product: Optional[str] = None
    application_id: Optional[str] = None
    name: Optional[str] = None


class SubscriptionPhase(BaseModel):
    """Subscription phase data"""

    uid: Optional[str] = None
    cadence: Optional[str] = None
    periods: Optional[int] = None
    recurring_price_money: Optional[Money] = None
    ordinal: Optional[int] = None


class CatalogQuickAmount(BaseModel):
    """Quick amount data"""

    type: Optional[str] = None
    amount: Optional[Money] = None
    score: Optional[int] = None
    ordinal: Optional[int] = None


class CatalogCustomAttributeDefinitionStringConfig(BaseModel):
    """String config for custom attribute definition"""

    enforce_uniqueness: Optional[bool] = None


class CatalogCustomAttributeDefinitionNumberConfig(BaseModel):
    """Number config for custom attribute definition"""

    precision: Optional[int] = None


class CatalogCustomAttributeDefinitionSelectionConfig(BaseModel):
    """Selection config for custom attribute definition"""

    max_allowed_selections: Optional[int] = None
    allowed_selections: Optional[List[Any]] = None


class CatalogCustomAttributeDefinition(BaseModel):
    """Data for a catalog custom attribute definition"""

    type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    source_application: Optional[SourceApplication] = None
    allowed_object_types: Optional[List[str]] = None
    seller_visibility: Optional[str] = None
    app_visibility: Optional[str] = None
    string_config: Optional[CatalogCustomAttributeDefinitionStringConfig] = None
    number_config: Optional[CatalogCustomAttributeDefinitionNumberConfig] = None
    selection_config: Optional[CatalogCustomAttributeDefinitionSelectionConfig] = None
    custom_attribute_usage_count: Optional[int] = None
    key: Optional[str] = None


class CatalogPricingRule(BaseModel):
    """Data for a catalog pricing rule"""

    name: Optional[str] = None
    time_period_ids: Optional[List[str]] = None
    discount_id: Optional[str] = None
    match_products_id: Optional[str] = None
    apply_products_id: Optional[str] = None
    exclude_products_id: Optional[str] = None
    valid_from_date: Optional[str] = None
    valid_from_local_time: Optional[str] = None
    valid_until_date: Optional[str] = None
    valid_until_local_time: Optional[str] = None
    exclude_strategy: Optional[str] = None
    minimum_order_subtotal_money: Optional[Money] = None
    customer_group_ids_any: Optional[List[str]] = None


class CatalogProductSet(BaseModel):
    """Data for a catalog product set"""

    name: Optional[str] = None
    product_ids_any: Optional[List[str]] = None
    product_ids_all: Optional[List[str]] = None
    quantity_exact: Optional[int] = None
    quantity_min: Optional[int] = None
    quantity_max: Optional[int] = None
    all_products: Optional[bool] = None


class CatalogTimePeriod(BaseModel):
    """Data for a catalog time period"""

    event: Optional[str] = None


class CatalogSubscriptionPlan(BaseModel):
    """Data for a catalog subscription plan"""

    name: Optional[str] = None
    phases: Optional[List[SubscriptionPhase]] = None
    subscription_plan_variations: Optional[List[Any]] = None
    eligible_item_ids: Optional[List[str]] = None
    eligible_category_ids: Optional[List[str]] = None
    all_items: Optional[bool] = None


class CatalogSubscriptionPlanVariation(BaseModel):
    """Data for a catalog subscription plan variation"""

    name: Optional[str] = None
    phases: Optional[List[SubscriptionPhase]] = None
    subscription_plan_id: Optional[str] = None
    monthly_billing_anchor_date: Optional[int] = None
    can_prorate: Optional[bool] = None
    successor_plan_variation_id: Optional[str] = None


class CatalogQuickAmountsSettings(BaseModel):
    """Data for catalog quick amounts settings"""

    option: Optional[str] = None
    eligible_for_auto_amounts: Optional[bool] = None
    amounts: Optional[List[CatalogQuickAmount]] = None


class CatalogAvailabilityPeriod(BaseModel):
    """Data for catalog availability period"""

    start_local_time: Optional[str] = None
    end_local_time: Optional[str] = None
    day_of_week: Optional[str] = None


class CatalogObjectBase(BaseModel):
    """Base class for all catalog objects with common fields"""

    id: str
    updated_at: Optional[datetime] = None
    version: Optional[int] = None
    is_deleted: Optional[bool] = None
    custom_attribute_values: Optional[Dict[str, CatalogCustomAttributeValue]] = None
    catalog_v1_ids: Optional[List[CatalogV1Id]] = None
    present_at_all_locations: Optional[bool] = None
    present_at_location_ids: Optional[List[str]] = None
    absent_at_location_ids: Optional[List[str]] = None


class CatalogItemObject(CatalogObjectBase):
    """Catalog object for items"""

    type: str = Field(default="ITEM")
    item_data: CatalogItem


class CatalogCategoryObject(CatalogObjectBase):
    """Catalog object for categories"""

    type: str = Field(default="CATEGORY")
    category_data: CatalogCategory


class CatalogItemVariationObject(CatalogObjectBase):
    """Catalog object for item variations"""

    type: str = Field(default="ITEM_VARIATION")
    item_variation_data: CatalogItemVariation


class CatalogTaxObject(CatalogObjectBase):
    """Catalog object for taxes"""

    type: str = Field(default="TAX")
    tax_data: CatalogTax


class CatalogDiscountObject(CatalogObjectBase):
    """Catalog object for discounts"""

    type: str = Field(default="DISCOUNT")
    discount_data: CatalogDiscount


class CatalogModifierListObject(CatalogObjectBase):
    """Catalog object for modifier lists"""

    type: str = Field(default="MODIFIER_LIST")
    modifier_list_data: CatalogModifierList


class CatalogModifierObject(CatalogObjectBase):
    """Catalog object for modifiers"""

    type: str = Field(default="MODIFIER")
    modifier_data: CatalogModifier


class CatalogImageObject(CatalogObjectBase):
    """Catalog object for images"""

    type: str = Field(default="IMAGE")
    image_data: CatalogImage


class CatalogMeasurementUnitObject(CatalogObjectBase):
    """Catalog object for measurement units"""

    type: str = Field(default="MEASUREMENT_UNIT")
    measurement_unit_data: CatalogMeasurementUnit


class CatalogItemOptionObject(CatalogObjectBase):
    """Catalog object for item options"""

    type: str = Field(default="ITEM_OPTION")
    item_option_data: CatalogItemOption


class CatalogItemOptionValueObject(CatalogObjectBase):
    """Catalog object for item option values"""

    type: str = Field(default="ITEM_OPTION_VAL")
    item_option_value_data: CatalogItemOptionValue


class CatalogCustomAttributeDefinitionObject(CatalogObjectBase):
    """Catalog object for custom attribute definitions"""

    type: str = Field(default="CUSTOM_ATTRIBUTE_DEFINITION")
    custom_attribute_definition_data: CatalogCustomAttributeDefinition


class CatalogPricingRuleObject(CatalogObjectBase):
    """Catalog object for pricing rules"""

    type: str = Field(default="PRICING_RULE")
    pricing_rule_data: CatalogPricingRule


class CatalogProductSetObject(CatalogObjectBase):
    """Catalog object for product sets"""

    type: str = Field(default="PRODUCT_SET")
    product_set_data: CatalogProductSet


class CatalogTimePeriodObject(CatalogObjectBase):
    """Catalog object for time periods"""

    type: str = Field(default="TIME_PERIOD")
    time_period_data: CatalogTimePeriod


class CatalogSubscriptionPlanObject(CatalogObjectBase):
    """Catalog object for subscription plans"""

    type: str = Field(default="SUBSCRIPTION_PLAN")
    subscription_plan_data: CatalogSubscriptionPlan


class CatalogSubscriptionPlanVariationObject(CatalogObjectBase):
    """Catalog object for subscription plan variations"""

    type: str = Field(default="SUBSCRIPTION_PLAN_VARIATION")
    subscription_plan_variation_data: CatalogSubscriptionPlanVariation


class CatalogQuickAmountsSettingsObject(CatalogObjectBase):
    """Catalog object for quick amounts settings"""

    type: str = Field(default="QUICK_AMOUNTS_SETTINGS")
    quick_amounts_settings_data: CatalogQuickAmountsSettings


class CatalogAvailabilityPeriodObject(CatalogObjectBase):
    """Catalog object for availability periods"""

    type: str = Field(default="AVAILABILITY_PERIOD")
    availability_period_data: CatalogAvailabilityPeriod


# Discriminated union of all catalog object types
CatalogObject = Union[
    CatalogItemObject,
    CatalogCategoryObject,
    CatalogItemVariationObject,
    CatalogTaxObject,
    CatalogDiscountObject,
    CatalogModifierListObject,
    CatalogModifierObject,
    CatalogImageObject,
    CatalogMeasurementUnitObject,
    CatalogItemOptionObject,
    CatalogItemOptionValueObject,
    CatalogCustomAttributeDefinitionObject,
    CatalogPricingRuleObject,
    CatalogProductSetObject,
    CatalogTimePeriodObject,
    CatalogSubscriptionPlanObject,
    CatalogSubscriptionPlanVariationObject,
    CatalogQuickAmountsSettingsObject,
    CatalogAvailabilityPeriodObject,
]

# Annotated discriminated union for proper type discrimination
CatalogObjectUnion = Annotated[
    Union[
        CatalogItemObject,
        CatalogCategoryObject,
        CatalogItemVariationObject,
        CatalogTaxObject,
        CatalogDiscountObject,
        CatalogModifierListObject,
        CatalogModifierObject,
        CatalogImageObject,
        CatalogMeasurementUnitObject,
        CatalogItemOptionObject,
        CatalogItemOptionValueObject,
        CatalogCustomAttributeDefinitionObject,
        CatalogPricingRuleObject,
        CatalogProductSetObject,
        CatalogTimePeriodObject,
        CatalogSubscriptionPlanObject,
        CatalogSubscriptionPlanVariationObject,
        CatalogQuickAmountsSettingsObject,
        CatalogAvailabilityPeriodObject,
    ],
    Field(discriminator="type"),
]


class CatalogListResponse(BaseModel):
    """Response model for the Square catalog list API"""

    objects: Optional[List[CatalogObject]] = None
    updated_at: Optional[datetime] = None
    cursor: Optional[str] = None
    errors: Optional[List["Error"]] = None


# Input models for tool integration
class ListCatalogInput(BaseModel):
    """Input model for listing catalog objects"""

    cursor: Optional[str] = Field(
        None, description="Pagination cursor returned in a previous response"
    )
    types: Optional[str] = Field(
        None,
        description="Comma-separated list of object types to retrieve (e.g., 'ITEM,CATEGORY')",
    )
    catalog_version: Optional[int] = Field(
        None, description="Specific version of the catalog to retrieve"
    )
    use_production: bool = Field(
        False,
        description="Whether to use production (True) or sandbox (False) environment",
    )


class SquareAccessToken(BaseModel):
    """Access token model for Square API authentication"""

    access_token: str = Field(..., description="The Square API access token")
    token_type: str = Field(
        default="Bearer", description="Token type (typically 'Bearer')"
    )


# ------------------- Search Models -------------------


class TextQuery(BaseModel):
    """Text query for catalog search"""

    keywords: List[str] = Field(
        ..., min_length=1, description="List of keywords to search for"
    )


class CatalogQuery(BaseModel):
    """Query object for catalog search"""

    text_query: Optional[TextQuery] = Field(
        None, description="Text query with keywords"
    )


class SearchCatalogInput(BaseModel):
    """Input model for searching catalog objects"""

    query: CatalogQuery = Field(
        ..., description="The query object containing search parameters"
    )
    object_types: Optional[List[str]] = Field(
        None,
        description="List of object types to search (e.g., ['ITEM', 'CATEGORY', 'MODIFIER'])",
    )
    include_related_objects: Optional[bool] = Field(
        True, description="Whether to include related objects in the response"
    )
    include_category_path_to_root: Optional[bool] = Field(
        False, description="Whether to include the full category path for categories"
    )
    limit: Optional[int] = Field(
        10, ge=1, le=1000, description="Maximum number of results to return (1-1000)"
    )
    use_production: bool = Field(
        default=False, description="Whether to use production environment"
    )


class CatalogSearchResponse(BaseModel):
    """Response model for the Square catalog search API"""

    objects: Optional[List[CatalogObject]] = None
    related_objects: Optional[List[CatalogObject]] = None
    latest_time: Optional[datetime] = None
    cursor: Optional[str] = None
    errors: Optional[List["Error"]] = None


# ------------------- Order Models -------------------


class OrderState(str, Enum):
    """Enum for order states"""

    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    DRAFT = "DRAFT"


class OrderSource(BaseModel):
    """The origination details of the order"""

    name: Optional[str] = None


class OrderQuantityUnit(BaseModel):
    """The measurement unit and decimal precision for quantity"""

    measurement_unit: Optional[MeasurementUnit] = None
    precision: Optional[int] = Field(None, ge=0, le=5)
    catalog_object_id: Optional[str] = None
    catalog_version: Optional[int] = None


class OrderLineItemItemType(str, Enum):
    """Enum for line item types"""

    ITEM = "ITEM"
    CUSTOM_AMOUNT = "CUSTOM_AMOUNT"
    GIFT_CARD = "GIFT_CARD"


class OrderLineItemDiscountType(str, Enum):
    """Enum for discount types"""

    UNKNOWN_DISCOUNT = "UNKNOWN_DISCOUNT"
    FIXED_PERCENTAGE = "FIXED_PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"
    VARIABLE_PERCENTAGE = "VARIABLE_PERCENTAGE"
    VARIABLE_AMOUNT = "VARIABLE_AMOUNT"


class OrderScope(str, Enum):
    """Enum for order-level vs line-item level scope"""

    ORDER = "ORDER"
    LINE_ITEM = "LINE_ITEM"


class OrderLineItemTaxType(str, Enum):
    """Enum for tax types"""

    UNKNOWN_TAX = "UNKNOWN_TAX"
    ADDITIVE = "ADDITIVE"
    INCLUSIVE = "INCLUSIVE"


# Aliases for backward compatibility and clarity
OrderLineItemDiscountScope = OrderScope
OrderLineItemTaxScope = OrderScope


class OrderServiceChargeCalculationPhase(str, Enum):
    """Enum for service charge calculation phase"""

    SUBTOTAL_PHASE = "SUBTOTAL_PHASE"
    TOTAL_PHASE = "TOTAL_PHASE"


class OrderServiceChargeType(str, Enum):
    """Enum for service charge type"""

    AUTO_GRATUITY = "AUTO_GRATUITY"
    CUSTOM = "CUSTOM"


class OrderServiceChargeTreatmentType(str, Enum):
    """Enum for service charge treatment type"""

    LINE_ITEM_TREATMENT = "LINE_ITEM_TREATMENT"
    APPORTIONED_TREATMENT = "APPORTIONED_TREATMENT"


# Reuse the consolidated scope enum
OrderServiceChargeScope = OrderScope


class FulfillmentType(str, Enum):
    """Enum for fulfillment types"""

    PICKUP = "PICKUP"
    SHIPMENT = "SHIPMENT"
    DELIVERY = "DELIVERY"


class FulfillmentState(str, Enum):
    """Enum for fulfillment states"""

    PROPOSED = "PROPOSED"
    RESERVED = "RESERVED"
    PREPARED = "PREPARED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


class FulfillmentLineItemApplication(str, Enum):
    """Enum for fulfillment line item application"""

    ALL = "ALL"
    ENTRY_LIST = "ENTRY_LIST"


class TenderType(str, Enum):
    """Enum for tender types"""

    CARD = "CARD"
    CASH = "CASH"
    THIRD_PARTY_CARD = "THIRD_PARTY_CARD"
    SQUARE_GIFT_CARD = "SQUARE_GIFT_CARD"
    NO_SALE = "NO_SALE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    WALLET = "WALLET"
    BUY_NOW_PAY_LATER = "BUY_NOW_PAY_LATER"
    SQUARE_ACCOUNT = "SQUARE_ACCOUNT"
    OTHER = "OTHER"


class RefundStatus(str, Enum):
    """Enum for refund status"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ErrorCategory(str, Enum):
    """Enum for error categories"""

    API_ERROR = "API_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    INVALID_REQUEST_ERROR = "INVALID_REQUEST_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    PAYMENT_METHOD_ERROR = "PAYMENT_METHOD_ERROR"
    REFUND_ERROR = "REFUND_ERROR"


# Supporting models


class Address(BaseModel):
    """Address information"""

    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    address_line_3: Optional[str] = None
    locality: Optional[str] = None
    sublocality: Optional[str] = None
    sublocality_2: Optional[str] = None
    sublocality_3: Optional[str] = None
    administrative_district_level_1: Optional[str] = None
    administrative_district_level_2: Optional[str] = None
    administrative_district_level_3: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class OrderLineItemAppliedTax(BaseModel):
    """Applied tax reference for line items"""

    uid: Optional[str] = Field(None, max_length=60)
    tax_uid: str = Field(..., min_length=1, max_length=60)
    applied_money: Optional[Money] = None


class OrderLineItemAppliedDiscount(BaseModel):
    """Applied discount reference for line items"""

    uid: Optional[str] = Field(None, max_length=60)
    discount_uid: str = Field(..., min_length=1, max_length=60)
    applied_money: Optional[Money] = None


class OrderLineItemAppliedServiceCharge(BaseModel):
    """Applied service charge reference for line items"""

    uid: Optional[str] = Field(None, max_length=60)
    service_charge_uid: str = Field(..., min_length=1, max_length=60)
    applied_money: Optional[Money] = None


class OrderLineItemPricingBlocklistsBlockedDiscount(BaseModel):
    """Blocked discount for line item pricing"""

    uid: Optional[str] = Field(None, max_length=60)
    discount_uid: Optional[str] = Field(None, max_length=60)
    discount_catalog_object_id: Optional[str] = Field(None, max_length=192)


class OrderLineItemPricingBlocklistsBlockedTax(BaseModel):
    """Blocked tax for line item pricing"""

    uid: Optional[str] = Field(None, max_length=60)
    tax_uid: Optional[str] = Field(None, max_length=60)
    tax_catalog_object_id: Optional[str] = Field(None, max_length=192)


class OrderLineItemPricingBlocklists(BaseModel):
    """Pricing blocklists for line items"""

    blocked_discounts: Optional[List[OrderLineItemPricingBlocklistsBlockedDiscount]] = (
        None
    )
    blocked_taxes: Optional[List[OrderLineItemPricingBlocklistsBlockedTax]] = None


class OrderLineItemModifier(BaseModel):
    """Modifier applied to a line item"""

    uid: Optional[str] = Field(None, max_length=60)
    catalog_object_id: Optional[str] = Field(None, max_length=192)
    catalog_version: Optional[int] = None
    name: Optional[str] = Field(None, max_length=255)
    quantity: Optional[str] = None
    base_price_money: Optional[Money] = None
    total_price_money: Optional[Money] = None
    metadata: Optional[Dict[str, str]] = None


class OrderLineItemTax(BaseModel):
    """Tax applied to an order"""

    uid: Optional[str] = Field(None, max_length=60)
    catalog_object_id: Optional[str] = Field(None, max_length=192)
    catalog_version: Optional[int] = None
    name: Optional[str] = Field(None, max_length=255)
    type: Optional[OrderLineItemTaxType] = None
    percentage: Optional[str] = Field(None, max_length=10)
    metadata: Optional[Dict[str, str]] = None
    applied_money: Optional[Money] = None
    scope: Optional[OrderLineItemTaxScope] = None
    auto_applied: Optional[bool] = None


class OrderLineItemDiscount(BaseModel):
    """Discount applied to an order"""

    uid: Optional[str] = Field(None, max_length=60)
    catalog_object_id: Optional[str] = Field(None, max_length=192)
    catalog_version: Optional[int] = None
    name: Optional[str] = Field(None, max_length=255)
    type: Optional[OrderLineItemDiscountType] = None
    percentage: Optional[str] = Field(None, max_length=10)
    amount_money: Optional[Money] = None
    applied_money: Optional[Money] = None
    metadata: Optional[Dict[str, str]] = None
    scope: Optional[OrderLineItemDiscountScope] = None
    reward_ids: Optional[List[str]] = None
    pricing_rule_id: Optional[str] = None


class OrderLineItem(BaseModel):
    """Line item in an order"""

    uid: Optional[str] = Field(None, max_length=60)
    name: Optional[str] = Field(None, max_length=512)
    quantity: str = Field(..., min_length=1, max_length=12)
    quantity_unit: Optional[OrderQuantityUnit] = None
    note: Optional[str] = Field(None, max_length=2000)
    catalog_object_id: Optional[str] = Field(None, max_length=192)
    catalog_version: Optional[int] = None
    variation_name: Optional[str] = Field(None, max_length=400)
    item_type: Optional[OrderLineItemItemType] = None
    metadata: Optional[Dict[str, str]] = None
    modifiers: Optional[List[OrderLineItemModifier]] = None
    applied_taxes: Optional[List[OrderLineItemAppliedTax]] = None
    applied_discounts: Optional[List[OrderLineItemAppliedDiscount]] = None
    applied_service_charges: Optional[List[OrderLineItemAppliedServiceCharge]] = None
    base_price_money: Optional[Money] = None
    variation_total_price_money: Optional[Money] = None
    gross_sales_money: Optional[Money] = None
    total_tax_money: Optional[Money] = None
    total_discount_money: Optional[Money] = None
    total_money: Optional[Money] = None
    pricing_blocklists: Optional[OrderLineItemPricingBlocklists] = None
    total_service_charge_money: Optional[Money] = None


class OrderServiceCharge(BaseModel):
    """Service charge applied to an order"""

    uid: Optional[str] = Field(None, max_length=60)
    name: Optional[str] = Field(None, max_length=512)
    catalog_object_id: Optional[str] = Field(None, max_length=192)
    catalog_version: Optional[int] = None
    percentage: Optional[str] = Field(None, max_length=10)
    amount_money: Optional[Money] = None
    applied_money: Optional[Money] = None
    total_money: Optional[Money] = None
    total_tax_money: Optional[Money] = None
    calculation_phase: Optional[OrderServiceChargeCalculationPhase] = None
    taxable: Optional[bool] = None
    applied_taxes: Optional[List[OrderLineItemAppliedTax]] = None
    metadata: Optional[Dict[str, str]] = None
    type: Optional[OrderServiceChargeType] = None
    treatment_type: Optional[OrderServiceChargeTreatmentType] = None
    scope: Optional[OrderServiceChargeScope] = None


class FulfillmentRecipient(BaseModel):
    """Recipient information for fulfillment"""

    customer_id: Optional[str] = None
    display_name: Optional[str] = None
    email_address: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[Address] = None


class FulfillmentPickupDetails(BaseModel):
    """Pickup details for fulfillment"""

    recipient: Optional[FulfillmentRecipient] = None
    expires_at: Optional[str] = None
    auto_complete_duration: Optional[str] = None
    schedule_type: Optional[str] = None
    pickup_at: Optional[str] = None
    pickup_window_duration: Optional[str] = None
    prep_time_duration: Optional[str] = None
    note: Optional[str] = None
    placed_at: Optional[str] = None
    accepted_at: Optional[str] = None
    rejected_at: Optional[str] = None
    ready_at: Optional[str] = None
    expired_at: Optional[str] = None
    picked_up_at: Optional[str] = None
    canceled_at: Optional[str] = None
    cancel_reason: Optional[str] = None
    is_curbside_pickup: Optional[bool] = None
    curbside_pickup_details: Optional[Dict[str, Any]] = None


class FulfillmentShipmentDetails(BaseModel):
    """Shipment details for fulfillment"""

    recipient: Optional[FulfillmentRecipient] = None
    carrier: Optional[str] = None
    shipping_note: Optional[str] = None
    shipping_type: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    placed_at: Optional[str] = None
    in_progress_at: Optional[str] = None
    packaged_at: Optional[str] = None
    expected_shipped_at: Optional[str] = None
    shipped_at: Optional[str] = None
    canceled_at: Optional[str] = None
    cancel_reason: Optional[str] = None
    failed_at: Optional[str] = None
    failure_reason: Optional[str] = None


class FulfillmentDeliveryDetails(BaseModel):
    """Delivery details for fulfillment"""

    recipient: Optional[FulfillmentRecipient] = None
    schedule_type: Optional[str] = None
    placed_at: Optional[str] = None
    deliver_at: Optional[str] = None
    prep_time_duration: Optional[str] = None
    delivery_window_duration: Optional[str] = None
    note: Optional[str] = None
    completed_at: Optional[str] = None
    in_progress_at: Optional[str] = None
    rejected_at: Optional[str] = None
    ready_at: Optional[str] = None
    delivered_at: Optional[str] = None
    canceled_at: Optional[str] = None
    cancel_reason: Optional[str] = None
    courier_pickup_at: Optional[str] = None
    courier_pickup_window_duration: Optional[str] = None
    is_no_contact_delivery: Optional[bool] = None
    dropoff_notes: Optional[str] = None
    courier_provider_name: Optional[str] = None
    courier_support_phone_number: Optional[str] = None
    square_delivery_id: Optional[str] = None
    external_delivery_id: Optional[str] = None
    managed_delivery: Optional[bool] = None


class FulfillmentFulfillmentEntry(BaseModel):
    """Fulfillment entry for specific line items"""

    uid: Optional[str] = None
    line_item_uid: str
    quantity: str
    metadata: Optional[Dict[str, str]] = None


class Fulfillment(BaseModel):
    """Order fulfillment details"""

    uid: Optional[str] = Field(None, max_length=60)
    type: Optional[FulfillmentType] = None
    state: Optional[FulfillmentState] = None
    line_item_application: Optional[FulfillmentLineItemApplication] = None
    entries: Optional[List[FulfillmentFulfillmentEntry]] = None
    metadata: Optional[Dict[str, str]] = None
    pickup_details: Optional[FulfillmentPickupDetails] = None
    shipment_details: Optional[FulfillmentShipmentDetails] = None
    delivery_details: Optional[FulfillmentDeliveryDetails] = None


class OrderRoundingAdjustment(BaseModel):
    """Rounding adjustment for an order"""

    uid: Optional[str] = Field(None, max_length=60)
    name: Optional[str] = None
    amount_money: Optional[Money] = None


class OrderMoneyAmounts(BaseModel):
    """Money amounts rollup"""

    total_money: Optional[Money] = None
    tax_money: Optional[Money] = None
    discount_money: Optional[Money] = None
    tip_money: Optional[Money] = None
    service_charge_money: Optional[Money] = None


class OrderReturnLineItem(BaseModel):
    """Line item being returned"""

    uid: Optional[str] = None
    source_line_item_uid: Optional[str] = None
    name: Optional[str] = None
    quantity: str
    quantity_unit: Optional[OrderQuantityUnit] = None
    note: Optional[str] = None
    catalog_object_id: Optional[str] = None
    catalog_version: Optional[int] = None
    variation_name: Optional[str] = None
    item_type: Optional[OrderLineItemItemType] = None
    return_modifiers: Optional[List[OrderLineItemModifier]] = None
    applied_taxes: Optional[List[OrderLineItemAppliedTax]] = None
    applied_discounts: Optional[List[OrderLineItemAppliedDiscount]] = None
    base_price_money: Optional[Money] = None
    variation_total_price_money: Optional[Money] = None
    gross_return_money: Optional[Money] = None
    total_tax_money: Optional[Money] = None
    total_discount_money: Optional[Money] = None
    total_money: Optional[Money] = None
    applied_service_charges: Optional[List[OrderLineItemAppliedServiceCharge]] = None
    total_service_charge_money: Optional[Money] = None


class OrderReturnServiceCharge(BaseModel):
    """Service charge being returned"""

    uid: Optional[str] = None
    source_service_charge_uid: Optional[str] = None
    name: Optional[str] = None
    catalog_object_id: Optional[str] = None
    catalog_version: Optional[int] = None
    percentage: Optional[str] = None
    amount_money: Optional[Money] = None
    applied_money: Optional[Money] = None
    total_money: Optional[Money] = None
    total_tax_money: Optional[Money] = None
    calculation_phase: Optional[OrderServiceChargeCalculationPhase] = None
    taxable: Optional[bool] = None
    applied_taxes: Optional[List[OrderLineItemAppliedTax]] = None


class OrderReturnTax(BaseModel):
    """Tax being returned"""

    uid: Optional[str] = None
    source_tax_uid: Optional[str] = None
    catalog_object_id: Optional[str] = None
    catalog_version: Optional[int] = None
    name: Optional[str] = None
    type: Optional[OrderLineItemTaxType] = None
    percentage: Optional[str] = None
    applied_money: Optional[Money] = None
    scope: Optional[OrderLineItemTaxScope] = None


class OrderReturnDiscount(BaseModel):
    """Discount being returned"""

    uid: Optional[str] = None
    source_discount_uid: Optional[str] = None
    catalog_object_id: Optional[str] = None
    catalog_version: Optional[int] = None
    name: Optional[str] = None
    type: Optional[OrderLineItemDiscountType] = None
    percentage: Optional[str] = None
    amount_money: Optional[Money] = None
    applied_money: Optional[Money] = None
    scope: Optional[OrderLineItemDiscountScope] = None


class OrderReturnTip(BaseModel):
    """Tip being returned"""

    uid: Optional[str] = None
    applied_money: Optional[Money] = None
    source_tender_uid: Optional[str] = None
    source_tender_id: Optional[str] = None


class OrderReturn(BaseModel):
    """Order return details"""

    uid: Optional[str] = Field(None, max_length=60)
    source_order_id: Optional[str] = None
    return_line_items: Optional[List[OrderReturnLineItem]] = None
    return_service_charges: Optional[List[OrderReturnServiceCharge]] = None
    return_taxes: Optional[List[OrderReturnTax]] = None
    return_discounts: Optional[List[OrderReturnDiscount]] = None
    return_tips: Optional[List[OrderReturnTip]] = None
    rounding_adjustment: Optional[OrderRoundingAdjustment] = None
    return_amounts: Optional[OrderMoneyAmounts] = None


class AdditionalRecipient(BaseModel):
    """Additional recipient for payments"""

    location_id: str
    description: str
    amount_money: Money
    receivable_id: Optional[str] = None


class TenderCardDetails(BaseModel):
    """Card tender details"""

    status: Optional[str] = None
    card: Optional[Dict[str, Any]] = None
    entry_method: Optional[str] = None


class TenderCashDetails(BaseModel):
    """Cash tender details"""

    buyer_tendered_money: Optional[Money] = None
    change_back_money: Optional[Money] = None


class TenderBankAccountDetails(BaseModel):
    """Bank account tender details"""

    status: Optional[str] = None


class TenderBuyNowPayLaterDetails(BaseModel):
    """Buy now pay later tender details"""

    buy_now_pay_later_brand: Optional[str] = None
    status: Optional[str] = None


class TenderSquareAccountDetails(BaseModel):
    """Square account tender details"""

    status: Optional[str] = None


class Tender(BaseModel):
    """Payment tender"""

    id: Optional[str] = Field(None, max_length=192)
    location_id: Optional[str] = Field(None, max_length=50)
    transaction_id: Optional[str] = Field(None, max_length=192)
    created_at: Optional[str] = Field(None, max_length=32)
    note: Optional[str] = Field(None, max_length=500)
    amount_money: Optional[Money] = None
    tip_money: Optional[Money] = None
    processing_fee_money: Optional[Money] = None
    customer_id: Optional[str] = Field(None, max_length=191)
    type: TenderType
    card_details: Optional[TenderCardDetails] = None
    cash_details: Optional[TenderCashDetails] = None
    bank_account_details: Optional[TenderBankAccountDetails] = None
    buy_now_pay_later_details: Optional[TenderBuyNowPayLaterDetails] = None
    square_account_details: Optional[TenderSquareAccountDetails] = None
    additional_recipients: Optional[List[AdditionalRecipient]] = None
    payment_id: Optional[str] = Field(None, max_length=192)


class Refund(BaseModel):
    """Order refund"""

    id: str = Field(..., max_length=255)
    location_id: str = Field(..., max_length=50)
    transaction_id: Optional[str] = Field(None, max_length=192)
    tender_id: str = Field(..., max_length=192)
    created_at: Optional[str] = Field(None, max_length=32)
    reason: str = Field(..., max_length=192)
    amount_money: Money
    status: RefundStatus
    processing_fee_money: Optional[Money] = None
    additional_recipients: Optional[List[AdditionalRecipient]] = None


class OrderPricingOptions(BaseModel):
    """Pricing options for an order"""

    auto_apply_discounts: Optional[bool] = None
    auto_apply_taxes: Optional[bool] = None


class OrderReward(BaseModel):
    """Reward applied to an order"""

    id: str = Field(..., min_length=1)
    reward_tier_id: str = Field(..., min_length=1)


class Order(BaseModel):
    """Square order object"""

    id: Optional[str] = None
    location_id: str = Field(..., min_length=1)
    reference_id: Optional[str] = Field(None, max_length=40)
    source: Optional[OrderSource] = None
    customer_id: Optional[str] = Field(None, max_length=191)
    line_items: Optional[List[OrderLineItem]] = None
    taxes: Optional[List[OrderLineItemTax]] = None
    discounts: Optional[List[OrderLineItemDiscount]] = None
    service_charges: Optional[List[OrderServiceCharge]] = None
    fulfillments: Optional[List[Fulfillment]] = None
    returns: Optional[List[OrderReturn]] = None
    return_amounts: Optional[OrderMoneyAmounts] = None
    net_amounts: Optional[OrderMoneyAmounts] = None
    rounding_adjustment: Optional[OrderRoundingAdjustment] = None
    tenders: Optional[List[Tender]] = None
    refunds: Optional[List[Refund]] = None
    metadata: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    state: Optional[OrderState] = None
    version: Optional[int] = None
    total_money: Optional[Money] = None
    total_tax_money: Optional[Money] = None
    total_discount_money: Optional[Money] = None
    total_tip_money: Optional[Money] = None
    total_service_charge_money: Optional[Money] = None
    ticket_name: Optional[str] = Field(None, max_length=30)
    pricing_options: Optional[OrderPricingOptions] = None
    rewards: Optional[List[OrderReward]] = None
    net_amount_due_money: Optional[Money] = None


class Error(BaseModel):
    """Error object"""

    category: ErrorCategory
    code: Optional[str] = None
    detail: Optional[str] = None
    field: Optional[str] = None


# Input and Output models for Create Order API


class CreateOrderInput(BaseModel):
    """Input model for creating an order"""

    order: Order = Field(..., description="The order to create")
    idempotency_key: Optional[str] = Field(
        None, max_length=192, description="Idempotency key for the request"
    )
    use_production: bool = Field(
        default=False, description="Whether to use production environment"
    )


class CreateOrderResponse(BaseModel):
    """Response model for the Square create order API"""

    order: Optional[Order] = None
    errors: Optional[List[Error]] = None


# ------------------- Payment Link Models -------------------


class QuickPay(BaseModel):
    """Describes an ad hoc item and price for which to generate a quick pay checkout link"""

    name: str = Field(
        ..., min_length=1, max_length=255, description="The ad hoc item name"
    )
    price_money: Money = Field(..., description="The price of the item")
    location_id: str = Field(
        ..., min_length=1, description="The ID of the business location"
    )


class CustomField(BaseModel):
    """Custom field requesting information from the buyer"""

    title: str = Field(
        ..., min_length=1, max_length=50, description="The title of the custom field"
    )


class AcceptedPaymentMethods(BaseModel):
    """The methods allowed for buyers during checkout"""

    apple_pay: Optional[bool] = Field(
        None, description="Whether Apple Pay is accepted at checkout"
    )
    google_pay: Optional[bool] = Field(
        None, description="Whether Google Pay is accepted at checkout"
    )
    cash_app_pay: Optional[bool] = Field(
        None, description="Whether Cash App Pay is accepted at checkout"
    )
    afterpay_clearpay: Optional[bool] = Field(
        None, description="Whether Afterpay/Clearpay is accepted at checkout"
    )


class ShippingFee(BaseModel):
    """The fee associated with shipping to be applied to the Order as a service charge"""

    name: Optional[str] = Field(None, description="The name for the shipping fee")
    charge: Money = Field(
        ..., description="The amount and currency for the shipping fee"
    )


class CheckoutOptions(BaseModel):
    """Describes optional fields to add to the resulting checkout page"""

    allow_tipping: Optional[bool] = Field(
        None, description="Indicates whether the payment allows tipping"
    )
    custom_fields: Optional[List[CustomField]] = Field(
        None,
        max_length=2,
        description="The custom fields requesting information from the buyer",
    )
    subscription_plan_id: Optional[str] = Field(
        None,
        max_length=255,
        description="The ID of the subscription plan for the buyer",
    )
    redirect_url: Optional[str] = Field(
        None,
        max_length=2048,
        description="The confirmation page URL to redirect the buyer to",
    )
    merchant_support_email: Optional[str] = Field(
        None,
        max_length=256,
        description="The email address that buyers can use to contact the seller",
    )
    ask_for_shipping_address: Optional[bool] = Field(
        None,
        description="Indicates whether to include the address fields in the payment form",
    )
    accepted_payment_methods: Optional[AcceptedPaymentMethods] = Field(
        None, description="The methods allowed for buyers during checkout"
    )
    app_fee_money: Optional[Money] = Field(
        None, description="The amount of money that the developer is taking as a fee"
    )
    shipping_fee: Optional[ShippingFee] = Field(
        None, description="The fee associated with shipping"
    )
    enable_coupon: Optional[bool] = Field(
        None, description="Indicates whether to include the Add coupon section"
    )
    enable_loyalty: Optional[bool] = Field(
        None, description="Indicates whether to include the REWARDS section"
    )


class PrePopulatedData(BaseModel):
    """Describes buyer data to prepopulate on the checkout page"""

    buyer_email: Optional[str] = Field(
        None, max_length=256, description="The buyer email to prepopulate"
    )
    buyer_phone_number: Optional[str] = Field(
        None, max_length=17, description="The buyer phone number to prepopulate"
    )
    buyer_address: Optional[Address] = Field(
        None, description="The buyer address to prepopulate"
    )


class PaymentLinkRelatedResources(BaseModel):
    """The list of related objects"""

    orders: Optional[List[Order]] = Field(
        None, description="The order associated with the payment link"
    )
    subscription_plans: Optional[List[CatalogObject]] = Field(
        None, description="The subscription plan associated with the payment link"
    )


class PaymentLink(BaseModel):
    """The created payment link"""

    id: Optional[str] = Field(
        None, description="The Square-assigned ID of the payment link"
    )
    version: int = Field(
        ..., le=65535, description="The Square-assigned version number"
    )
    description: Optional[str] = Field(
        None,
        max_length=4096,
        description="The optional description of the payment_link object",
    )
    order_id: Optional[str] = Field(
        None,
        max_length=192,
        description="The ID of the order associated with the payment link",
    )
    checkout_options: Optional[CheckoutOptions] = Field(
        None, description="The checkout options configured for the payment link"
    )
    url: Optional[str] = Field(
        None, max_length=255, description="The shortened URL of the payment link"
    )
    long_url: Optional[str] = Field(
        None, max_length=255, description="The long URL of the payment link"
    )
    created_at: Optional[str] = Field(
        None, description="The timestamp when the payment link was created"
    )
    updated_at: Optional[str] = Field(
        None, description="The timestamp when the payment link was last updated"
    )
    payment_note: Optional[str] = Field(
        None, max_length=500, description="An optional note"
    )
    related_resources: Optional[PaymentLinkRelatedResources] = Field(
        None, description="The list of related objects"
    )


class CreatePaymentLinkInput(BaseModel):
    """Input model for creating a payment link"""

    idempotency_key: Optional[str] = Field(
        None, max_length=192, description="A unique string that identifies this request"
    )
    description: Optional[str] = Field(
        None, max_length=4096, description="A description of the payment link"
    )
    quick_pay: Optional[QuickPay] = Field(
        None, description="Describes an ad hoc item and price for quick pay checkout"
    )
    location_id: Optional[str] = Field(
        None, min_length=1, description="The ID of the business location"
    )
    order: Optional[Order] = Field(
        None, description="Describes the Order for which to create a checkout link"
    )
    checkout_options: Optional[CheckoutOptions] = Field(
        None, description="Optional fields to add to the resulting checkout page"
    )
    pre_populated_data: Optional[PrePopulatedData] = Field(
        None, description="Fields to prepopulate in the resulting checkout page"
    )
    payment_note: Optional[str] = Field(
        None, max_length=500, description="A note for the payment"
    )
    use_production: bool = Field(
        default=False, description="Whether to use production environment"
    )


class CreatePaymentLinkResponse(BaseModel):
    """Response model for the Square create payment link API"""

    errors: Optional[List[Error]] = Field(
        None, description="Any errors that occurred during the request"
    )
    payment_link: Optional[PaymentLink] = Field(
        None, description="The created payment link"
    )


class SquareFoodItem(BaseModel):
    """Food item extracted from chat history for Square ordering"""

    item_name: str = Field(
        ...,
        description="Complete item name including modifications, size, and customizations from the menu",
    )
    quantity: int = Field(default=1, gt=0, description="Quantity of this item")


class SquareFoodItemList(BaseModel):
    """List of food items extracted from chat history"""

    items: List[SquareFoodItem] = Field(
        ..., description="List of food items the customer wants to order"
    )


class GetCatalogObjectInput(BaseModel):
    """Input model for retrieving a catalog object"""

    object_id: str = Field(..., description="The ID of the catalog object to retrieve")
    catalog_version: Optional[int] = Field(
        None, description="Specific version of the catalog object to retrieve"
    )
    include_category_path_to_root: Optional[bool] = Field(
        False, description="Whether to include the full category path for categories"
    )
    include_related_objects: Optional[bool] = Field(
        True, description="Whether to include related objects in the response"
    )
    use_production: bool = Field(
        default=True,
        description="Whether to use production API (True) or sandbox (False)",
    )


class GetCatalogObjectResponse(BaseModel):
    """Response model for the Square get catalog object API"""

    object: Optional[CatalogObject] = Field(
        None, description="The requested catalog object"
    )
    related_objects: Optional[List[CatalogObject]] = Field(
        None, description="Related objects included in the response"
    )
    errors: Optional[List[Error]] = Field(
        None, description="Any errors that occurred during the request"
    )


class ItemModifierExtraction(BaseModel):
    """Extracted modifier information from chat history"""

    modifier_name: str = Field(..., description="Exact modifier name from menu")
    modifier_id: Optional[str] = Field(
        None, description="Square modifier ID extracted from catalog documents"
    )


class ExtractedItemWithModifiers(BaseModel):
    """Extracted item with modifiers from chat history"""

    item_name: str = Field(
        ..., description="Complete item name exactly as it appears in the menu"
    )
    item_id: Optional[str] = Field(
        None, description="Square item ID extracted from catalog documents"
    )
    variation_id: Optional[str] = Field(
        None, description="Square variation ID extracted from catalog documents"
    )
    quantity: int = Field(default=1, gt=0, description="Quantity of this item")
    modifiers: List[ItemModifierExtraction] = Field(
        default=[], description="List of modifiers for this item"
    )
    special_notes: Optional[str] = Field(
        None, description="Any special requests or notes"
    )


class ExtractedOrderWithModifiers(BaseModel):
    """Extracted order with items and modifiers from chat history"""

    items: List[ExtractedItemWithModifiers] = Field(
        ..., description="List of items with their modifiers"
    )
