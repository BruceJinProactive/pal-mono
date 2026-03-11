"""Monitoring Service.

Provides business logic for monitoring configuration and run CRUD operations.
"""

from ._business_hours import (
    BusinessHoursCheckResult,
    is_within_business_hours,
    parse_captured_at,
)
from ._implementation import (
    build_config_response,
    build_run_list_response,
    build_run_response,
    cleanup_reference_images,
    create_config,
    delete_config,
    delete_run,
    delete_runs_batch,
    get_config,
    get_configs,
    get_run,
    get_runs,
    test_monitoring_config,
    trigger_run,
    update_config,
    upload_reference_images,
)
from ._llm import (
    create_monitoring_run_with_analysis,
    create_monitoring_video_run_with_analysis,
    generate_monitoring_llm_prompt,
    generate_monitoring_video_llm_prompt,
)
from ._time_window import is_within_time_window, parse_time, should_skip_monitoring

__all__ = [
    "create_config",
    "get_configs",
    "get_config",
    "update_config",
    "delete_config",
    "trigger_run",
    "get_runs",
    "get_run",
    "delete_run",
    "delete_runs_batch",
    "build_config_response",
    "build_run_response",
    "build_run_list_response",
    "upload_reference_images",
    "cleanup_reference_images",
    "generate_monitoring_llm_prompt",
    "generate_monitoring_video_llm_prompt",
    "create_monitoring_run_with_analysis",
    "create_monitoring_video_run_with_analysis",
    "parse_time",
    "is_within_time_window",
    "should_skip_monitoring",
    "test_monitoring_config",
]
