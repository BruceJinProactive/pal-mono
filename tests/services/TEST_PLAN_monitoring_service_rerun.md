# Test Plan: Monitoring Service Rerun Functionality

This document describes the test coverage needed for the rerun monitoring functionality implemented in `services/monitoring_service/_implementation.py`.

## Test File Location
`tests/services/test_monitoring_service_rerun.py`

## Functions to Test

1. **`rerun_monitoring_run()`** - Main service function
2. **`_rerun_monitoring_analysis_background()`** - Background task

##  Test Cases for `rerun_monitoring_run()`

### ✅ Test: Manual Run with s3_key Only
**Purpose**: Verify runs created by manual trigger (which store `s3_key`) can be rerun

**Setup**:
- Mock run with `trigger_metadata = {"s3_key": "test-bucket/image.jpg"}`
- Mock config, feed (image type)
- Patch: `db.repositories.MonitoringRunRepositoryAsync`, `db.repositories.MonitoringConfigRepositoryAsync`, `db.repositories.SignalFeedRepositoryAsync`

**Assertions**:
- Returns `{"run_id": ..., "monitoring_config_id": ..., "status": "processing"}`
- `MonitoringRunRepositoryAsync.update()` called with processing status
- `asyncio.create_task()` called to spawn background task
- `session.commit()` called

### ✅ Test: Automated Run with image_url
**Purpose**: Verify runs with `image_url` (automated triggers) work

**Setup**:
- Mock run with `trigger_metadata = {"image_url": "test-bucket/image.jpg"}`

**Assertions**:
- Same as above

### ✅ Test: Video Run with video_url
**Purpose**: Verify video runs work with `video_url`

**Setup**:
- Mock run with `trigger_metadata = {"video_url": "test-bucket/video.mp4"}`
- Mock feed with `feed_type = FeedType.video_stream`

**Assertions**:
- Background task spawned with `is_video=True`

### ✅ Test: Missing Media Reference Raises Error
**Purpose**: Verify error when no media URL exists

**Setup**:
- Mock run with `trigger_metadata = {"trigger_source": "manual"}` (no media keys)

**Assertions**:
- Raises `ValueError` with message mentioning "image_url, video_url, and s3_key"

### ✅ Test: Nonexistent Run Raises Error
**Purpose**: Verify error when run_id doesn't exist

**Setup**:
- `MonitoringRunRepositoryAsync.get_by_id()` returns `None`

**Assertions**:
- Raises `ValueError` with "not found"

### ✅ Test: Wrong Project Raises Error
**Purpose**: Verify authorization - run must belong to project

**Setup**:
- Mock run and config with different `project_id`

**Assertions**:
- Raises `ValueError` with "does not belong to project"

### ✅ Test: Duplicate Rerun Attempts (Idempotency)
**Purpose**: Verify multiple reruns don't cause issues

**Setup**:
- Call `rerun_monitoring_run()` twice with same run_id
- Patch `asyncio.create_task()` to track calls

**Assertions**:
- Both calls succeed
- Two background tasks created independently
- No database conflicts

## Test Cases for `_rerun_monitoring_analysis_background()`

### ✅ Test: Image Analysis Success
**Purpose**: Verify successful image analysis updates run

**Setup**:
- Patch: `db.get_db_async` (return mock session), `db.repositories.MonitoringRunRepositoryAsync`, `services.monitoring_service._llm.generate_monitoring_llm_prompt`
- Mock LLM returns `{"analysis_result": {"result": "pass", "details": "..."}}`

**Assertions**:
- `generate_monitoring_llm_prompt()` called with `image_url=media_url`
- `MonitoringRunRepositoryAsync.update()` called once
- Update includes `evaluation_result` with pass result
- Update includes `error_message=None`
- Update does NOT include `completed_at` (preserved from original)
- `session.commit()` called

### ✅ Test: Video Analysis Success
**Purpose**: Verify successful video analysis

**Setup**:
- `is_video=True`
- Patch `services.monitoring_service._llm.generate_monitoring_video_llm_prompt`
- Mock LLM returns fail result

**Assertions**:
- `generate_monitoring_video_llm_prompt()` called with `video_url=media_url`
- Update includes fail result

### ✅ Test: LLM Returns Error Result
**Purpose**: Verify handling of LLM error response

**Setup**:
- Mock LLM returns `{"analysis_result": {"result": "error", "details": "Timeout"}}`

**Assertions**:
- Update includes `evaluation_result` with error
- Update includes `error_message="Timeout"`

### ✅ Test: LLM Throws Exception
**Purpose**: Verify exception handling during LLM call

**Setup**:
- `generate_monitoring_llm_prompt()` raises `Exception("LLM unavailable")`

**Assertions**:
- `session.rollback()` called
- Run updated with error status: `{"result": "error", "details": "Rerun failed: ...", "status": "failed"}`
- `error_message` set to "Rerun failed: LLM unavailable"
- Exception logged (verify logger.error called)

### ✅ Test: Database Update Failure
**Purpose**: Verify handling when DB update fails

**Setup**:
- First `update()` call raises `Exception("DB connection lost")`
- Second `update()` call succeeds (for error status)

**Assertions**:
- `session.rollback()` called after first failure
- `update()` called twice: once for result (fails), once for error status (succeeds)
- Final update sets error status with "Rerun failed"

### ✅ Test: Commit Failure
**Purpose**: Verify handling when commit fails

**Setup**:
- `session.commit()` raises exception

**Assertions**:
- `session.rollback()` called
- Error logged

### ✅ Test: Preserves completed_at
**Purpose**: Verify `completed_at` timestamp is never modified

**Setup**:
- Successful analysis

**Assertions**:
- `update()` kwargs do NOT include `completed_at`
- `update()` kwargs include `evaluation_result` and `error_message`

## Patching Requirements

### For `rerun_monitoring_run()` tests:
```python
patch("db.repositories.MonitoringRunRepositoryAsync")
patch("db.repositories.MonitoringConfigRepositoryAsync")
patch("db.repositories.SignalFeedRepositoryAsync")
patch("asyncio.create_task")
```

### For `_rerun_monitoring_analysis_background()` tests:
```python
patch("db.get_db_async")  # Return mock async generator
patch("db.repositories.MonitoringRunRepositoryAsync")
patch("services.monitoring_service._llm.generate_monitoring_llm_prompt")  # For image
patch("services.monitoring_service._llm.generate_monitoring_video_llm_prompt")  # For video
```

## Running Tests

```bash
# Run in Docker (recommended - has all dependencies)
docker exec -it pal-mono-api pytest tests/services/test_monitoring_service_rerun.py -v

# Run locally (may require additional setup)
uv run pytest tests/services/test_monitoring_service_rerun.py -v
```

## Implementation Notes

1. **Mock FeedType enum**: For video detection, mock `feed.feed_type` to match `FeedType.video_stream` comparison
2. **Mock async generators**: Use `async def mock_get_db_async(): yield mock_session`
3. **Mock AsyncSession**: Use `AsyncMock()` with `commit` and `rollback` methods
4. **Assert logging**: Use `patch("utils.log.logger")` to verify error logging

## Success Criteria

- All test cases pass
- Code coverage >80% for rerun functions
- Tests run in <5 seconds
- No flaky tests (run 10 times, all pass)
