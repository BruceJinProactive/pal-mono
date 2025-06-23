from abc import abstractmethod

from cron._cron_job_base import CronJobBase
from cron._util import ScheduleType
from utils.log import logger


class CronJobDailyAt0100(CronJobBase):
    def __init__(self, job_name: str):
        super().__init__(ScheduleType.DAILY_AT_0100)
        self.job_name = job_name

    @abstractmethod
    async def run(self) -> None:
        """
        The main logic for the cron job goes here.
        Must be implemented by all subclasses.
        """
        pass

    async def pre_run(self) -> None:
        logger.info(
            f"[Cronjob]:{self.job_name} on {self.__class__.__name__} starts running"
        )

    async def post_run(self) -> None:
        logger.info(
            f"[Cronjob]:{self.job_name} on {self.__class__.__name__} finishs running"
        )
