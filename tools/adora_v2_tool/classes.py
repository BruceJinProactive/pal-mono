from pydantic import BaseModel, Field


class DeliveryAddress(BaseModel):
    address: str = Field(description="Street address")
    extended_address: str = Field(
        description="Extended address (if applicable)",
        default="",
        serialization_alias="extendedAddress",
    )
    city: str = Field(description="City name")
    state: str = Field(
        description="Two-letter US state abbreviation (e.g., 'CA', 'NY', 'TX')"
    )
    zip: str = Field(description="ZIP code")
    lat: float = Field(description="Latitude", default=0)
    lng: float = Field(description="Longitude", default=0)
    instruction: str = Field(
        description="Special instructions for the delivery address", default=""
    )
    type_id: int = Field(default=1, serialization_alias="typeId")
    extra_field_1: str = Field(
        description="Extra field 1", default="", serialization_alias="extraField1"
    )
    extra_field_2: str = Field(
        description="Extra field 2", default="", serialization_alias="extraField2"
    )
    zone_id: int = Field(default=0, serialization_alias="zoneId")
