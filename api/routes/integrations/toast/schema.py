from enum import StrEnum
from typing import Optional

from pydantic import BaseModel


class ToastWebhookRequest(BaseModel):
    """Request body for Toast webhook"""

    timestamp: str
    eventCategory: str
    eventType: str
    guid: str
    details: dict


class ToastWebhookResponse(BaseModel):
    """Response body for Toast webhook"""

    status: str = "Success"


class ToastWebhookMenuDetails(BaseModel):
    """Details of the menu updated event
    Example:
    {
        "restaurantGuid": "00000000-1111-2222-3333-444444444444",
        "publishedDate": "2021-10-06T20:11:01.737Z"
    }

    """

    restaurantGuid: str
    publishedDate: str


class ToastStockItemStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    QUANTITY = "QUANTITY"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class ToastWebhookStockItemDetails(BaseModel):
    """Details of the stock item updated event
    Example:
    {
      "itemGuid": "1e199622-ccbf-4ba8-8c37-111519dca13b",
      "restaurantGuid": "3325cc58-dc6e-4e21-85f9-7de275ffe820",
      "status": "IN_STOCK",
      "quantity": 10.0, (optional)
      "multiLocationId": "100000000171238879",
      "versionId": "1e199622-ccbf-4ba8-8c37-111519dca13b"
    }
    """

    itemGuid: str
    restaurantGuid: str
    status: ToastStockItemStatus
    multiLocationId: str
    versionId: str
    quantity: Optional[float] = None


class TimeRange(BaseModel):
    """Time range"""

    start: list[int]
    end: list[int]


class DayPeriod(BaseModel):
    """Day period"""

    day: str
    timeRanges: list[TimeRange]


class ServicePeriod(BaseModel):
    """Ordering schedule"""

    diningOptionBehavior: str
    dayPeriods: list[DayPeriod]


class Override(BaseModel):
    """Override"""

    description: str
    diningOptionBehavior: list[str]
    businessDate: int
    timeRanges: list[TimeRange]


class OrderingSchedule(BaseModel):
    """Ordering schedule"""

    servicePeriods: list[ServicePeriod]
    overrides: list[Override]
    scheduledOrderMaxDays: int
    lastOrderConfiguration: str


class ToastWebhookOrderingScheduleDetails(BaseModel):
    """Details of the ordering schedule updated event
      Example:
      {
      "restaurantGuid": "d6bf0376-cea1-47c0-a63c-9fc06638a5a6",
      "orderingSchedule": {
        "servicePeriods": [
          {
            "diningOptionBehavior": "DELIVERY",
            "dayPeriods": [
              {
                "day": "SATURDAY",
                "timeRanges": [
                  {
                    "start": [
                      12,
                      0
                    ],
                    "end": [
                      0,
                      0
                    ]
                  }
                ]
              },
              {
                "day": "SUNDAY",
                "timeRanges": [
                  {
                    "start": [
                      11,
                      0
                    ],
                    "end": [
                      23,
                      0
                    ]
                  }
                ]
              }
            ]
          },
          {
            "diningOptionBehavior": "TAKE_OUT",
            "dayPeriods": [
              {
                "day": "TUESDAY",
                "timeRanges": [
                  {
                    "start": [
                      8,
                      0
                    ],
                    "end": [
                      20,
                      0
                    ]
                  }
                ]
              },
              {
                "day": "WEDNESDAY",
                "timeRanges": [
                  {
                    "start": [
                      10,
                      0
                    ],
                    "end": [
                      20,
                      0
                    ]
                  }
                ]
              },
              {
                "day": "THURSDAY",
                "timeRanges": [
                  {
                    "start": [
                      12,
                      0
                    ],
                    "end": [
                      21,
                      0
                    ]
                  }
                ]
              }
            ]
          }
        ],
        "overrides": [
          {
            "description": "team party",
            "diningOptionBehavior": [
              "DELIVERY"
            ],
            "businessDate": 20250531,
            "timeRanges": [
              {
                "start": [
                  9,
                  0
                ],
                "end": [
                  21,
                  0
                ]
              }
            ]
          }
        ],
        "scheduledOrderMaxDays": 3,
        "lastOrderConfiguration": "UNTIL_CLOSING_TIME"
      }
    }
    """

    restaurantGuid: str
    orderingSchedule: OrderingSchedule
