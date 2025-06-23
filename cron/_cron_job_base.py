import datetime
import os
from abc import ABC, abstractmethod
from typing import final

from cron._util import ScheduleType


class CronJobBase(ABC):
    def __init__(self, schedule_type: ScheduleType):
        self.run_at = datetime.datetime.now(datetime.timezone.utc)
        self.schedule_type = schedule_type

    @abstractmethod
    async def run(self) -> None:
        """
        The main logic for the cron job goes here.
        Must be implemented by all subclasses.
        """
        pass

    async def pre_run(self) -> None:
        """
        Hook to run logic before the job starts.
        Optional to override.
        """
        pass

    async def post_run(self) -> None:
        """
        Hook to run logic after the job completes.
        Optional to override.
        """
        pass

    def should_execute(self) -> bool:
        schedule_type = os.environ.get("CRONJOB_SCHEDULE_TYPE")
        if not schedule_type:
            return False
        return self.schedule_type.lower() == schedule_type.lower()

    @final
    async def execute(self) -> None:
        """This defines the fixed execution flow. Should not be overridden."""
        if self.should_execute():
            await self.pre_run()
            await self.run()
            await self.post_run()
