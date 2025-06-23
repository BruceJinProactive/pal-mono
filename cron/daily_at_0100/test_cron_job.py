from cron.daily_at_0100._cron_job_daily_at_0100 import CronJobDailyAt0100
from utils.log import logger


class TestCronJob(CronJobDailyAt0100):
    def __init__(self):
        super().__init__("test_cron_job")

    async def run(self):
        logger.debug("[Cronjob] Running Test Job")
