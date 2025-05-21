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


class BaseCustomField(BaseModel):
    id: int
    isrequired: bool
    label: str
    scope: str
    validationregex: str
    value: str


class CustomField(BaseCustomField):
    pass


class BasketCustomField(BaseCustomField):
    pass


class CustomFieldInput(BaseModel):
    fieldid: int
    value: str


class SuggestedTipOption(BaseModel):
    default: bool
    value: int


class SuggestedTips(BaseModel):
    options: list[SuggestedTipOption]


class BaseTax(BaseModel):
    label: str
    tax: float


class Tax(BaseTax):
    pass


class TaxResult(BaseTax):
    pass


class BaseFee(BaseModel):
    amount: float
    description: str
    note: str


class Fee(BaseFee):
    pass


class OrderFee(BaseFee):
    pass


class BaseDonation(BaseModel):
    id: int
    amount: float
    description: str
    note: str
    detailednote: str
    imagepath: str


class Donation(BaseDonation):
    pass


class OrderDonation(BaseDonation):
    pass


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
    donations: list[Donation]
    earliestreadytime: str
    fees: list[Fee]
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


class UpsellImage(BaseModel):
    groupname: str
    description: str
    isdefault: bool
    filename: str
    url: Optional[str] = None


class UpsellItem(BaseModel):
    id: int
    name: str
    cost: str
    chainproductid: int
    shortdescription: str
    minquantity: int
    maxquantity: int
    images: list[UpsellImage]


class UpsellGroup(BaseModel):
    title: str
    items: list[UpsellItem]


class ContextualPricing(BaseModel):
    isposvalidated: bool
    issyndicated: bool


class ValidatedBasketTotals(BaseModel):
    basketid: str
    contextualpricing: Optional[ContextualPricing] = None
    tax: float
    taxes: list[Tax]
    customerhandoffcharge: float
    fees: list[Fee]
    donations: list[Donation]
    subtotal: float
    total: float
    readytime: str
    totalfees: float
    totaldonations: float
    upsellgroups: Optional[list[UpsellGroup]] = None
    posreferenceresponse: str
    taxexemptaccountidentifier: Optional[str] = None


class OloCCSFToken(BaseModel):
    accesstoken: str


class BillingFieldData(BaseModel):
    fieldid: int
    value: str


class BillingMethod(str, Enum):
    creditcard = "creditcard"
    creditcardonfile = "creditcardonfile"
    creditcardtoken = "creditcardtoken"
    billingaccount = "billingaccount"
    cash = "cash"
    payinstore = "payinstore"
    storedvalue = "storedvalue"
    prepaid = "prepaid"
    paymentsession = "paymentsession"
    digitalwallet = "digitalwallet"


class UserType(str, Enum):
    user = "user"
    guest = "guest"


class ReceivingUser(BaseModel):
    firstname: str
    lastname: str
    emailaddress: str
    contactnumber: str
    contactnumberextension: Optional[str] = None


class OloAccount(BaseModel):
    createaccount: bool


class OloOrderSubmissionBody(BaseModel):
    authtoken: Optional[str] = None
    billingmethod: BillingMethod
    billingaccountid: Optional[int] = None
    billingschemeid: Optional[str] = None
    billingfields: Optional[list[BillingFieldData]] = None
    usertype: UserType
    firstname: Optional[str] = None  # required for guest
    lastname: Optional[str] = None  # required for guest
    emailaddress: Optional[str] = None  # required for guest
    contactnumber: Optional[str] = None  # required for guest
    contactnumberextension: Optional[str] = None
    reference: Optional[str] = None
    cardnumber: Optional[str] = None
    expiryyear: Optional[int] = None
    expirymonth: Optional[int] = None
    cvv: Optional[str] = None
    streetaddress: Optional[str] = None
    streetaddress2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    saveonfile: Optional[str] = None
    saveguestuser: Optional[bool] = None
    createoloaccount: Optional[bool] = None
    oloaccount: Optional[OloAccount] = None
    orderref: Optional[str] = None
    prepaidtransactionid: Optional[str] = None
    prepaiddescription: Optional[str] = None
    guestoptin: Optional[bool] = None
    useroptintosms: Optional[bool] = None
    receivinguser: Optional[ReceivingUser] = None
    token: Optional[str] = None
    cardtype: Optional[str] = None
    cardlastfour: Optional[str] = None
    paymentsessionid: Optional[str] = None


class OrderStatus(str, Enum):
    COMPLETED = "Completed"
    CANCELED = "Canceled"
    TRANSMITTING = "Transmitting"
    SCHEDULED = "Scheduled"
    PENDING_MANUAL_FIRE = "Pending Manual Fire"
    IN_PROGRESS = "In Progress"


class TimeMode(str, Enum):
    ASAP = "asap"
    MANUAL_FIRE = "manualfire"
    ADVANCE = "advance"


class DeliveryMode(str, Enum):
    CURBSIDE = "curbside"
    DRIVETHRU = "drivethru"
    PICKUP = "pickup"
    DISPATCH = "dispatch"
    DELIVERY = "delivery"
    DINEIN = "dinein"
    UNSPECIFIED = "unspecified"


class ArrivalStatus(str, Enum):
    ORDER_PLACED = "Order Placed"
    ARRIVED = "Arrived"
    PICKED_UP = "Picked Up"


class TaxExemption(BaseModel):
    taxexemptaccountid: str
    taxexemptaccountidentifier: str


class ResponseDeliveryAddress(BaseModel):
    id: int
    building: Optional[str] = None
    streetaddress: str
    city: str
    zipcode: str
    phonenumber: str
    specialinstructions: Optional[str] = None
    isdefault: bool


class DiscountType(str, Enum):
    COUPON = "Coupon"
    LOYALTY = "Loyalty"
    BRAND_DISCOUNT = "BrandDiscount"
    SCHEDULED_PRICE = "ScheduledPrice"
    EXTERNAL = "External"
    COMP_CARD = "CompCard"
    POS = "Pos"
    SUBTOTAL_DISCOUNT = "SubtotalDiscount"


class Discount(BaseModel):
    discount: float
    description: str
    type: DiscountType


class OrderStatusProductChoice(BaseModel):
    id: int  # Olo option id. This is the option id from the restaurant's menu.
    chainchoiceid: int  # Olo's chain-wide option id.
    name: str  # Name of the option.
    quantity: float  # Quantity ordered of the option.


class OrderStatusProduct(BaseModel):
    id: int
    chainproductid: int
    name: str
    quantity: int
    totalcost: float
    specialinstructions: Optional[str] = None
    custompassthroughdata: Optional[str] = None
    choices: list[OrderStatusProductChoice]


class ResponseOloAuthStatus(BaseModel):
    created: bool


class OloOrderSubmissionResponse(BaseModel):
    id: str  # guid
    oloid: str
    vendorid: int
    status: OrderStatus
    subtotal: float
    salestax: float
    taxes: list[TaxResult]
    taxexemption: Optional[TaxExemption] = None
    fees: list[OrderFee]
    totalfees: float
    donations: list[OrderDonation]
    totaldonations: Optional[float] = None
    total: float
    timemode: TimeMode
    tip: float
    billingaccountid: Optional[str] = None
    billingaccountids: Optional[list[str]] = None
    contextualpricing: Optional[ContextualPricing] = None
    deliveryaddress: Optional[ResponseDeliveryAddress] = None
    customfields: list[BasketCustomField]
    iseditable: bool
    discount: float
    discounts: list[Discount]
    orderref: str
    timeplaced: str  # date-time yyyymmdd hh:mm
    readytime: str  # date-time yyyymmdd hh:mm
    vendorname: str
    vendorextref: str
    deliverymode: DeliveryMode
    customerhandoffcharge: Optional[float] = None
    arrivalstatus: Optional[ArrivalStatus] = None
    products: list[OrderStatusProduct]
    authtoken: Optional[str] = None
    oloaccountcreated: Optional[ResponseOloAuthStatus] = None
    cateringaccountid: Optional[str] = None  # guid
