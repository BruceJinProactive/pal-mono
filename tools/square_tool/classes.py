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
    errors: Optional[List[Any]] = None


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
