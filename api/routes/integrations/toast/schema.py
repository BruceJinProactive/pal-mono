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


class ToastPartnerEventType(StrEnum):
    PARTNER_ADDED = "partner_added"
    PARTNER_REMOVED = "partner_removed"
    PARTNER_UPDATED = "partner_updated"


class ToastWebhookPartnerDetails(BaseModel):
    """Details of the partner webhook events (partner_added, partner_removed, partner_updated)

    All three partner event types use the same payload structure.

    Example:
    {
        "restaurantGuid": "00000000-1111-2222-3333-444444444444",
        "managementGroupGuid": "55555555-6666-7777-8888-999999999999",
        "restaurantName": "Toast Grill & Tap",
        "locationName": "Fenway, Boston, MA",
        "externalGroupRef": null,
        "externalRestaurantRef": null,
        "modifiedDate": 1568667880240,
        "createdDate": 1568667880240,
        "isoModifiedDate": "2019-09-16T21:01:53.685Z",
        "isoCreatedDate": "2019-09-16T21:01:53.685Z",
        "createdByFirstName": "Toast",
        "createdByLastName": "Admin",
        "createdByEmailAddress": "admin@toasttab.com",
        "createdByPhoneNumber": null,
        "restaurantPhoneNumber": "6175551234",
        "restaurantAddressLine1": "401 Park Drive",
        "restaurantAddressLine2": null,
        "restaurantCity": "Boston",
        "restaurantState": "MA",
        "restaurantZipCode": "02215",
        "restaurantCountryCode": "US",
        "restaurantTimezone": "America/New_York",
        "restaurantLatitude": "42.344257",
        "restaurantLongitude": "-71.102181"
    }
    """

    restaurantGuid: str
    managementGroupGuid: Optional[str] = None
    restaurantName: str
    locationName: Optional[str] = None
    externalGroupRef: Optional[str] = None
    externalRestaurantRef: Optional[str] = None
    modifiedDate: int
    createdDate: int
    isoModifiedDate: str
    isoCreatedDate: str
    createdByFirstName: Optional[str] = None
    createdByLastName: Optional[str] = None
    createdByEmailAddress: Optional[str] = None
    createdByPhoneNumber: Optional[str] = None
    restaurantPhoneNumber: Optional[str] = None
    restaurantAddressLine1: Optional[str] = None
    restaurantAddressLine2: Optional[str] = None
    restaurantCity: Optional[str] = None
    restaurantState: Optional[str] = None
    restaurantZipCode: Optional[str] = None
    restaurantCountryCode: str
    restaurantTimezone: str
    restaurantLatitude: Optional[float] = None
    restaurantLongitude: Optional[float] = None
