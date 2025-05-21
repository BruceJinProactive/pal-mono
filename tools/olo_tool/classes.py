from enum import Enum
from typing import Optional

from pydantic import BaseModel


######### OLO API CLASS START ############
class OloAccessToken(BaseModel):
    access_token: str
    expires_in: Optional[int] = None
    token_type: str = "OloKey"

    def get_token_header_value(self) -> str:
        return f"{self.token_type} {self.access_token}"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class OloHubResponse(BaseModel):
    status: int
    reason: str
    decoded_body: str


class CustomField(BaseModel):
    id: int
    isrequired: bool
    label: str
    scope: str
    validationregex: str
    value: str


class SuggestedTipOption(BaseModel):
    default: bool
    value: int


class SuggestedTips(BaseModel):
    options: list[SuggestedTipOption]


class Tax(BaseModel):
    label: str
    tax: float


class OloBasket(BaseModel):
    allowsmsorderupdates: bool
    allowstip: bool
    appliedrewards: list
    cateringaccountid: Optional[str] = None
    contactnumber: Optional[str] = None
    contextualpricing: Optional[dict] = None
    coupon: Optional[str] = None
    coupondiscount: float
    coupons: list
    customerhandoffcharge: float
    customfields: list[CustomField]
    deliveryaddress: Optional[dict] = None
    deliverymode: str
    discount: float
    discounts: list
    dispatchoptions: Optional[dict] = None
    donations: list
    earliestreadytime: str
    fees: list
    id: str
    isupsellenabled: bool
    leadtimeestimateminutes: int
    mode: str
    onpremisedetails: Optional[dict] = None
    products: list
    salestax: float
    subtotal: float
    suggestedtipamount: float
    suggestedtippercentage: int
    suggestedtips: SuggestedTips
    taxes: list[Tax]
    taxexemption: Optional[dict] = None
    timemode: str
    timewanted: Optional[str] = None
    tip: float
    total: float
    totaldonations: float
    totalfees: float
    validationmessages: list
    vendorid: int
    vendoronline: bool
    wasupsold: bool


class RestaurantCustomLabel(BaseModel):
    key: str
    value: str


class OloStore(BaseModel):
    id: int
    name: str
    brand: Optional[str] = None
    storename: str
    telephone: str
    streetaddress: str
    streetaddress2: Optional[str] = None
    crossstreet: Optional[str] = None
    city: str
    contextualpricing: Optional[dict] = None
    state: str
    zip: str
    country: str
    latitude: float
    longitude: float
    locationid: Optional[str] = None
    utcoffset: int
    url: str
    mobileurl: str
    distance: Optional[float] = None
    extref: Optional[str] = None
    advanceonly: bool
    advanceorderdays: int
    allowstaxexemption: bool
    supportscoupons: bool
    supportsloyalty: bool
    supportedcardtypes: str
    supportsmanualfire: bool
    candeliver: bool
    canpickup: bool
    supportscurbside: bool
    supportsdispatch: bool
    supportsdinein: bool
    hasolopass: bool
    deliveryarea: Optional[str] = None
    minimumdeliveryorder: Optional[float] = None
    maximumdeliveryorder: Optional[float] = None
    minimumpickuporder: Optional[float] = None
    maximumpayinstoreorder: Optional[float] = None
    deliveryfee: Optional[float] = None
    deliveryfeetiers: Optional[list[dict]] = None
    supportstip: bool
    supportsspecialinstructions: bool
    specialinstructionsmaxlength: Optional[int] = None
    supportsguestordering: bool
    requiresphonenumber: bool
    supportsonlineordering: bool
    supportsnationalmenu: bool
    supportsfeedback: bool
    supportssplitpayments: bool
    slug: str
    isavailable: bool
    iscurrentlyopen: bool
    deliverydelayalertenabled: bool
    deliverydelayalertmessage: Optional[str] = None
    supportsgrouporders: bool
    supportsproductrecipientnames: bool
    supportsbaskettransfers: bool
    allowhandoffchoiceatmanualfire: bool
    orderingurls: Optional[list[dict]] = None
    productrecipientnamelabel: Optional[str] = None
    customerfacingmessage: Optional[str] = None
    availabilitymessage: Optional[str] = None
    supportsdrivethru: bool
    showcalories: bool
    acceptsordersuntilclosing: bool
    acceptsordersbeforeopening: bool
    suggestedtippercentage: Optional[int] = None
    customfields: Optional[list[dict]] = None
    labels: Optional[list[RestaurantCustomLabel]] = None
    metadata: Optional[list[dict]] = None
    supportedtimemodes: list[str]
    attributes: Optional[list[str]] = None
    supportedcountries: list[str]
    supportedarrivalmessagehandoffmodes: Optional[list[str]] = None
    calendars: Optional[list[dict]] = None


class CustomFieldInput(BaseModel):
    fieldid: int
    value: str


class ChoiceInput(BaseModel):
    choiceid: int
    quantity: int
    customfields: Optional[list[CustomFieldInput]] = None


class ProductInput(BaseModel):
    productid: int
    quantity: int
    specialinstructions: Optional[str] = None
    recipient: Optional[str] = None
    customdata: Optional[dict] = None
    choices: Optional[list[ChoiceInput]] = None
    isupsell: Optional[bool] = None


class OloProductInput(BaseModel):
    products: list[ProductInput]
    replacebasketcontents: bool


class OloBasketHandoffMode(str, Enum):
    delivery = "delivery"
    dispatch = "dispatch"
    curbside = "curbside"
    pickup = "pickup"
    dinein = "dinein"
    drivethru = "drivethru"
