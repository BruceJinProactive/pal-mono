import os

from mixpanel import Mixpanel

from api.schemas.admin.analytics import Event as AnalyticsEvent


def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
    mp = None
    if MIXPANEL_PROJECT_TOKEN:
        mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)

    if mp:
        mp.track(user_id, event_name, event_properties)
