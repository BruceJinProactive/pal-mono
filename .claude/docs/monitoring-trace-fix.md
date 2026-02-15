# Fix Plan: Isolate Monitoring LLM Traces from Voice Agent Traces

## Problem

Monitoring LLM calls (image/video analysis) are inheriting active voice-agent trace context, so Datadog LLMObs spans appear inside voice trace trees.

Current suppression in `/services/monitoring_service/_providers.py` uses `Pin.remove_from(self.client)`, which is ineffective and relies on private ddtrace APIs.

## Scope

In scope:
1. Isolate monitoring LLM calls into independent traces in `/services/monitoring_service/_llm.py`.
2. Remove dead Pin-based tracing code from `/services/monitoring_service/_providers.py`.
3. Update and extend tests to cover new behavior.

Out of scope for this PR:
1. Changing global LLMObs bootstrap behavior in `/agent/agent.py`.
2. Broad tracing refactors outside monitoring service.

Follow-up cleanup (separate PR):
1. Evaluate whether `LLMObs.enable()` in `/agent/agent.py` should be removed after validating all Agent entry points.

## Implementation Checklist

### 1) Add trace isolation wrapper for image analysis

File: `/services/monitoring_service/_llm.py`

1. Add `from ddtrace.trace import tracer`.
2. Replace direct `run_in_executor(... lambda: provider.analyze_image(...))` with a wrapper function executed in the executor.
3. In wrapper:
   1. Capture current context: `current_context = tracer.current_trace_context()`.
   2. Clear inherited context: `tracer.context_provider.activate(None)`.
   3. Create explicit monitoring span:
      1. Operation: `monitoring.llm.analyze_image`
      2. Service: `pal-mono-monitoring`
      3. Tags:
         1. `monitoring.config_id`
         2. `monitoring.llm_provider`
         3. `monitoring.llm_model`
         4. `monitoring.media_type=image`
   4. Call `provider.analyze_image(...)`.
   5. In `finally`, always restore original context (`tracer.context_provider.activate(current_context)`).

### 2) Add trace isolation wrapper for video analysis

File: `/services/monitoring_service/_llm.py`

1. Apply same wrapper pattern around `provider.analyze_video_frames(...)`.
2. Use:
   1. Operation: `monitoring.llm.analyze_video_frames`
   2. Service: `pal-mono-monitoring`
   3. Tags:
      1. `monitoring.config_id`
      2. `monitoring.llm_provider`
      3. `monitoring.llm_model`
      4. `monitoring.media_type=video`
      5. `monitoring.video_frames_count`

### 3) Remove dead Pin code

File: `/services/monitoring_service/_providers.py`

1. Remove `from ddtrace._trace.pin import Pin`.
2. Remove Azure Pin block in provider init.
3. Remove Google Pin block in provider init.
4. Update nearby comments so they no longer claim tracing is disabled in provider clients.

### 4) Update tests for provider cleanup

File: `/services/monitoring_service/tests/test_providers.py`

1. Remove `Pin.get_from` mocks in provider factory tests.
2. Keep constructor tests focused on client creation/config behavior.

### 5) Add tests for trace-isolation behavior

File: `/services/monitoring_service/tests/test_llm.py`

Add unit tests for both image and video prompt-generation paths to verify:
1. `tracer.current_trace_context()` is read.
2. Context is cleared before provider call.
3. New span is created with expected operation/service.
4. Expected monitoring tags are set.
5. Original context is restored in `finally`.
6. Context restore happens even when provider call raises.

Implementation notes:
1. Mock `create_monitoring_llm_provider`, S3 reads, and executor loop to avoid external I/O.
2. Use a fake span context manager to assert tag writes deterministically.

## Reference Pattern

Use `/services/routine_submission_service/_llm.py:246` as the baseline pattern for context isolation and restoration.

## Verification Plan

### Automated

1. `docker exec -it pal-mono-api pytest services/monitoring_service/tests/test_providers.py`
2. `docker exec -it pal-mono-api pytest services/monitoring_service/tests/test_llm.py`
3. `./scripts/validate.sh`

### Manual (staging)

1. Trigger one monitoring image run and one monitoring video run.
2. Verify in Datadog:
   1. Monitoring LLM calls start a separate root trace (new trace ID, not child of voice request trace).
   2. Monitoring root span uses service `pal-mono-monitoring`.
   3. Voice-agent traces no longer include monitoring LLM spans.
3. Validate no regression:
   1. Voice request traces still include normal voice LLM spans.
   2. Monitoring runs still save evaluation results as before.

## Rollout / Safety

1. Deploy behind normal release process (no flag required).
2. If unexpected trace behavior appears, revert only monitoring `_llm.py` isolation changes (provider Pin removal is safe/no-op behavior removal).
