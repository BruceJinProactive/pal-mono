from datetime import datetime, timezone


class RequestContext:
    def __init__(self):
        self.request_time = datetime.now(timezone.utc)
