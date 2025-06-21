import asyncio
import os

from cron import test_job
from utils.log import configure_global_logger, patch_agno_logger_to_use_root


async def main():
    configure_global_logger()
    patch_agno_logger_to_use_root()

    job_name = os.environ.get("CRON_JOB_NAME", "test_job")
    if job_name == "test_job":
        await test_job.run()
    else:
        raise ValueError(f"Unknown job: {job_name}")


if __name__ == "__main__":
    asyncio.run(main())
