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
