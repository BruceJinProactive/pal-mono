# PAL-9097: Add audio recording upload endpoint to pal-mono internal voice API

## Context

Option B approach: LiveKit agent POSTs audio to pal-mono, which uploads to S3 using its existing
IAM role. Avoids exposing AWS credentials to LiveKit Cloud infrastructure.

**Flow:**
```
LiveKit Agent → POST /v1/internal/voice/upload-recording (multipart)
                    → pal-mono uploads to S3
                    → returns {"audio_recording_s3_uri": "s3://..."}
Agent includes URI in VoiceCallEndReport → existing end-call flow (PAL-8480) publishes event
```

## Repo

`pal-mono` — work in new worktree `pal-mono-9097`

## Dependencies

- None (can start immediately)
- PAL-8480 (PR #3687) consumes the S3 URI downstream but is independent

## Implementation Steps

### 1. Create worktree and branch

```bash
cd C:\Users\acock\palona\pal-mono
git worktree add ../pal-mono-9097 -b PAL-9097-audio-upload-endpoint
```

### 2. Add route decorator — `api/routes/internal/voice.py`

Add a third endpoint to `voice_router`:

```python
@voice_router.post("/upload-recording", status_code=status.HTTP_201_CREATED)
async def upload_recording(
    file: UploadFile = File(...),
    call_id: str = Form(...),
    room_name: str = Form(...),
) -> dict:
    """Upload an audio recording from the LiveKit agent worker."""
    return await _voice.upload_recording(file, call_id, room_name)
```

No `AsyncSession` dependency needed — this endpoint only interacts with S3, not the database.

Follow existing pattern: decorators in `voice.py`, implementation in `_voice.py`.

### 3. Add implementation — `api/routes/internal/_voice.py`

Add `upload_recording()` function. Key decisions grounded in codebase patterns:

- **S3 client**: Use `init_s3(AWS_REGION)` from `services/asset_service/_utils.py` (existing pattern)
- **Upload method**: `put_object` with `Body=bytes` (file is <4MB — no need for streaming
  `upload_fileobj` which is used for 500MB videos)
- **Thread offload**: `run_in_threadpool(s3_client.put_object, ...)` to avoid blocking async loop
  (matches video upload pattern)
- **Bucket**: Use `AWS_ASSET_BUCKET_NAME` env var (existing `{env}-pal-mono-bucket`)
- **S3 key**: `recordings/{room_name}/{call_id}.ogg` (matches PAL-8478 investigation spec and
  what the evaluator expects)
- **Auth**: None (matches existing internal voice endpoints — TODO comment for VPC-only access)

```python
import os
from fastapi import File, Form, UploadFile, HTTPException, status
from starlette.concurrency import run_in_threadpool
from services.asset_service._utils import init_s3

_MAX_AUDIO_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_EXTENSIONS = {".ogg", ".wav", ".mp3"}

async def upload_recording(
    file: UploadFile,
    call_id: str,
    room_name: str,
) -> dict:
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower() if file.filename else ".ogg"
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format '{ext}'. Allowed: {_ALLOWED_EXTENSIONS}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > _MAX_AUDIO_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {_MAX_AUDIO_FILE_SIZE // (1024*1024)} MB",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Upload to S3
    bucket = os.getenv("AWS_ASSET_BUCKET_NAME", "local-bucket")
    region = os.getenv("AWS_REGION", "us-east-1")
    s3_key = f"recordings/{room_name}/{call_id}{ext}"

    s3_client = init_s3(region)
    await run_in_threadpool(
        s3_client.put_object,
        Bucket=bucket,
        Key=s3_key,
        Body=content,
        ContentType=file.content_type or "audio/ogg",
    )

    s3_uri = f"s3://{bucket}/{s3_key}"
    logger.info(
        "[upload_recording] Audio uploaded to S3",
        extra={"call_id": call_id, "room_name": room_name, "s3_uri": s3_uri, "size_bytes": len(content)},
    )
    return {"audio_recording_s3_uri": s3_uri}
```

### 4. Add imports to `voice.py`

Add `File, Form, UploadFile` imports from `fastapi` (if not already present).

### 5. Write tests — `tests/api/routes/internal/test_voice_upload_recording.py`

New test file (matches naming pattern of existing `test_voice_end_call_event.py`).

**Test cases:**

| Test | What it verifies |
|---|---|
| `test_upload_recording_success` | Happy path: valid OGG file → 201 + S3 URI returned |
| `test_upload_recording_returns_correct_s3_path` | S3 key is `recordings/{room_name}/{call_id}.ogg` |
| `test_upload_recording_empty_file` | 400 for zero-byte file |
| `test_upload_recording_too_large` | 413 for file >10MB |
| `test_upload_recording_unsupported_extension` | 400 for `.exe`, `.txt`, etc. |
| `test_upload_recording_missing_call_id` | 422 for missing required form field |
| `test_upload_recording_missing_room_name` | 422 for missing required form field |
| `test_upload_recording_s3_failure` | 500 when S3 `put_object` raises `ClientError` |

Mock `init_s3` to avoid real S3 calls. Use `httpx.AsyncClient` with `TestClient` pattern matching
existing test files.

### 6. Run validation

```bash
cd C:\Users\acock\palona\pal-mono-9097
uv run pre-commit run --all-files
uv run pytest tests/api/routes/internal/test_voice_upload_recording.py -v
```

## Files Changed

| File | Change |
|---|---|
| `api/routes/internal/voice.py` | Add `upload_recording` route decorator |
| `api/routes/internal/_voice.py` | Add `upload_recording()` implementation |
| `tests/api/routes/internal/test_voice_upload_recording.py` | **New** — endpoint tests |

## Files NOT Changed

| File | Why |
|---|---|
| `api/schemas/internal/voice_init.py` | No Pydantic request model needed — using `File()` + `Form()` directly |
| `events/schema.py` | No event schema changes — PAL-8480 handles event publishing |
| `services/asset_service/` | Reusing existing `init_s3()` — no new service code |
| `api/routes/internal/__init__.py` | `voice_router` already registered — no routing changes |

## Potential Concerns

- **No auth on internal endpoints**: Existing pattern — flagged with TODO in codebase. Not in scope.
- **File in memory**: `content = await file.read()` loads full file. Fine for <4MB audio but
  wouldn't scale to large files. Acceptable given recordings are ~720KB typical.
- **S3 bucket naming**: Uses `AWS_ASSET_BUCKET_NAME` (existing bucket). Recordings land in
  `recordings/` prefix which PAL-8481 already grants read access for.
- **No deduplication**: Re-uploading same call_id overwrites. Acceptable — idempotent behavior.

## Estimated Time

~1.5h implementation + tests
