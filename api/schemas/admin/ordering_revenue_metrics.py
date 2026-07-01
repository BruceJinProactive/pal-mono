from pydantic import BaseModel, Field


class OrderingRevenueAmountBucket(BaseModel):
    """Order count and value for a revenue segment."""

    orders: int = Field(..., description="Number of orders in this segment")
    revenue: float = Field(..., description="Order value in dollars for this segment")


class OrderingRevenueFulfillmentBucket(OrderingRevenueAmountBucket):
    """Order count, value, and share for a fulfillment segment."""

    share: float | None = Field(
        ..., description="Percent share of all orders in the selected period"
    )


class OrderingRevenueSummary(BaseModel):
    """Aggregate revenue metrics for the selected period."""

    total_orders: int = Field(..., description="Total orders in the selected period")
    palona_revenue: float = Field(
        ..., description="Paid order value in dollars for the selected period"
    )
    palona_aov: float = Field(
        ..., description="Average order value across all created orders"
    )


class OrderingRevenueTimeSeriesPoint(BaseModel):
    """Daily revenue metrics for dashboard charts."""

    date: str = Field(..., description="Metric date in YYYY-MM-DD format")
    total_orders: int = Field(..., description="Number of orders created that day")
    palona_revenue: float = Field(
        ..., description="Palona-attributed revenue for the day"
    )
    palona_aov: float = Field(..., description="Average order value for the day")
    payment_link_orders: int = Field(
        ..., description="Paid orders with Palona payment-link evidence"
    )
    payment_link_revenue: float = Field(
        ..., description="Paid order value with Palona payment-link evidence"
    )
    pay_in_store_orders: int = Field(
        ..., description="Orders attributed to store collection"
    )
    pay_in_store_revenue: float = Field(
        ..., description="Order value attributed to store collection"
    )
    takeout_orders: int = Field(..., description="Takeout order count")
    delivery_orders: int = Field(..., description="Delivery order count")


class OrderingRevenuePaymentPath(BaseModel):
    """Order value split by inferred payment path."""

    payment_link: OrderingRevenueAmountBucket = Field(
        ...,
        description="Paid orders with Palona payment-link evidence",
    )
    pay_in_store: OrderingRevenueAmountBucket = Field(
        ...,
        description=(
            "Adora orders without payment-link evidence and Toast paid orders without "
            "Palona payment-link evidence"
        ),
    )


class OrderingRevenueFulfillment(BaseModel):
    """Created order value split by fulfillment strategy."""

    takeout: OrderingRevenueFulfillmentBucket
    delivery: OrderingRevenueFulfillmentBucket


class OrderingRevenueStore(BaseModel):
    """Store-level revenue row."""

    store_id: str | None = Field(..., description="External store/location identifier")
    store_name: str = Field(..., description="Display name for the store/location")
    project_id: str | None = Field(..., description="Project UUID, if available")
    project_name: str | None = Field(
        ..., description="Project display name, if available"
    )
    orders: int = Field(..., description="Total orders for this store")
    palona_revenue: float = Field(..., description="Paid order value for this store")
    palona_aov: float = Field(..., description="Average order value for this store")
    payment_link: OrderingRevenueAmountBucket
    pay_in_store: OrderingRevenueAmountBucket


class OrderingRevenueMetricsResponse(BaseModel):
    """Revenue dashboard metrics for an account/project scope."""

    account_name: str = Field(..., description="Account identifier")
    ordering_enabled: bool = Field(
        ..., description="Whether ordering is enabled for this account/project scope"
    )
    period_start: str = Field(..., description="Start date in YYYY-MM-DD format")
    period_end: str = Field(..., description="End date in YYYY-MM-DD format")
    summary: OrderingRevenueSummary
    time_series: list[OrderingRevenueTimeSeriesPoint] = Field(default_factory=list)
    payment_path: OrderingRevenuePaymentPath
    fulfillment: OrderingRevenueFulfillment
    stores: list[OrderingRevenueStore] = Field(default_factory=list)
