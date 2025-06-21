import asyncio
import os

from . import test_job


async def main():
    job_name = os.environ.get("CRON_JOB_NAME", "test_job")
    if job_name == "test_job":
        await test_job.run()
    else:
        raise ValueError(f"Unknown job: {job_name}")


if __name__ == "__main__":
    asyncio.run(main())
