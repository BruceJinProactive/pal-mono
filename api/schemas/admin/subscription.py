from pydantic import AnyHttpUrl, BaseModel, EmailStr, PositiveInt, field_validator


class CheckoutParams(BaseModel):
    account_name: str
    customer_email: EmailStr
    price_id: str
    redirect_url_prefix: AnyHttpUrl
    quantity: PositiveInt = 1

    @field_validator("price_id")
    def validate_price_id(cls, v):
        if not v.startswith("price_"):
            raise ValueError('Price ID must start with "price_"')
        return v
