from pydantic import BaseModel, Field


class OrderingMetricPoint(BaseModel):
    """Daily ordering metrics for dashboard charts."""

    date: str = Field(..., description="Metric date in YYYY-MM-DD format")
    total_orders: int = Field(..., description="Number of orders created that day")
    total_order_value: float = Field(..., description="Total order value in dollars")
    order_accuracy: float | None = Field(
        ..., description="Percent of order calls without tool call errors"
    )
    order_call_count: int = Field(
        ..., description="Number of distinct conversations with orders"
    )
    accurate_order_call_count: int = Field(
        ..., description="Number of order conversations without tool call errors"
    )
    tool_error_order_call_count: int = Field(
        ..., description="Number of order conversations with at least one tool error"
    )


class OrderingMetricSummary(BaseModel):
    """Aggregate ordering metrics for the selected period."""

    total_orders: int = Field(..., description="Total orders in the selected period")
    total_order_value: float = Field(
        ..., description="Total order value in dollars for the selected period"
    )
    order_accuracy: float | None = Field(
        ..., description="Period-level percent of order calls without tool errors"
    )
    order_call_count: int = Field(
        ..., description="Distinct conversations with orders in the selected period"
    )
    accurate_order_call_count: int = Field(
        ..., description="Order conversations without tool call errors"
    )
    tool_error_order_call_count: int = Field(
        ..., description="Order conversations with at least one tool error"
    )


class OrderingMetricsResponse(BaseModel):
    """Ordering dashboard metrics and account/project ordering capability gate."""

    account_name: str = Field(..., description="Account identifier")
    ordering_enabled: bool = Field(
        ..., description="Whether ordering is enabled for this account/project scope"
    )
    period_start: str = Field(..., description="Start date in YYYY-MM-DD format")
    period_end: str = Field(..., description="End date in YYYY-MM-DD format")
    time_series: list[OrderingMetricPoint] = Field(default_factory=list)
    summary: OrderingMetricSummary
