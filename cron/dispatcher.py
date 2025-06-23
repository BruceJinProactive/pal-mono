import asyncio
import os

from cron.daily_at_0100.test_cron_job import TestCronJob
from utils.log import configure_global_logger, patch_agno_logger_to_use_root


async def main():
    configure_global_logger()
    patch_agno_logger_to_use_root()

    schedule_type = os.environ.get("CRONJOB_SCHEDULE_TYPE")
    if not schedule_type:
        raise ValueError("CRONJOB_SCHEDULE_TYPE is missing")

    cronjobs = [TestCronJob]

    for job in cronjobs:
        await job().execute()


if __name__ == "__main__":
    asyncio.run(main())
