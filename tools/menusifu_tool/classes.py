"""
MenuSifu Tool classes
"""

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class LocalizedName(BaseModel):
    """Localized name with English and Chinese"""

    en: Optional[str] = None
    zh_cn: Optional[str] = Field(None, alias="zh-cn")

    class Config:
        allow_population_by_field_name = True


class SubOption(BaseModel):
    """Sub-option within an option"""

    id: int
    name: LocalizedName
    price: Union[int, float]
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")

    class Config:
        allow_population_by_field_name = True


class Option(BaseModel):
    """Option for menu items or categories"""

    id: int
    name: LocalizedName
    price: Optional[Union[int, float]] = None
    short_name: Optional[LocalizedName] = Field(None, alias="shortName")
    max_num_of_item_option_allowed: Optional[int] = Field(
        None, alias="maxNumOfItemOptionAllowed"
    )
    sub_options: Optional[List[SubOption]] = Field(None, alias="subOptions")

    class Config:
        allow_population_by_field_name = True


class Tax(BaseModel):
    """Tax information"""

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

    class Config:
        allow_population_by_field_name = True


class Property(BaseModel):
    """Item property"""

    display_name: Optional[str] = Field(None, alias="displayName")
    name: Optional[str] = None
    value: Optional[bool] = None

    class Config:
        allow_population_by_field_name = True


class Size(BaseModel):
    """Size information for detailed pricing"""

    en: Optional[str] = None
    zh_cn: Optional[str] = Field(None, alias="zh-cn")

    class Config:
        allow_population_by_field_name = True


class Price(BaseModel):
    """Price information with size and order type"""

    id: int
    order_type: str = Field(alias="orderType")
    price: Union[int, float]
    size: Size
    size_id: int = Field(alias="sizeId")

    class Config:
        allow_population_by_field_name = True


class DetailPrice(BaseModel):
    """Detailed pricing information with different sizes"""

    prices: List[Price]


class ComboSectionSaleItem(BaseModel):
    """Sale item within a combo section"""

    pre_selected: bool = Field(alias="preSelected")
    sale_item_id: int = Field(alias="saleItemId")

    class Config:
        allow_population_by_field_name = True


class ComboSection(BaseModel):
    """Combo section information"""

    id: int
    name: LocalizedName
    allow_repeated_items: Optional[bool] = Field(None, alias="allowRepeatedItems")
    combo_section_sale_items: List[ComboSectionSaleItem] = Field(
        alias="comboSectionSaleItems"
    )
    item_selection_rule: int = Field(alias="itemSelectionRule")
    max_num_of_selection_allowed: int = Field(alias="maxNumOfSelectionAllowed")
    min_num_of_selection_allowed: int = Field(alias="minNumOfSelectionAllowed")
    price_rule: int = Field(alias="priceRule")

    class Config:
        allow_population_by_field_name = True


class SaleItem(BaseModel):
    """Menu sale item"""

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
    base_price: Optional[int] = Field(None, alias="basePrice")
    combo_sections: Optional[List[ComboSection]] = Field(None, alias="comboSections")

    # Additional fields
    detail_price: Optional[DetailPrice] = Field(None, alias="detailPrice")
    options: Optional[List[Option]] = None
    properties: Optional[List[Property]] = None

    class Config:
        allow_population_by_field_name = True


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
