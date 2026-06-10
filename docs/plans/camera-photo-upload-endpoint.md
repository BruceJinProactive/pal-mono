# Camera Photo Upload Endpoint

## Context

The security camera system on the VM captures RTSP video segments and uploads them via the existing
`upload-video` endpoint. We now need a parallel path for **JPEG snapshots** captured every 15 seconds,
enabling near-real-time vision analysis without processing full video streams.

**Flow:**

```
VM (camera_manager.py) → ffmpeg captures 1 frame/15s → POST /v1/operation/.../upload-photo (multipart)
                            → pal-mono uploads to S3 (images bucket)
                            → updates SignalFeed.last_capture_at
                            → returns {"url": "s3-key"}
```

## Architecture Decisions

- **Separate S3 bucket**: Photos go to `AWS_IMAGE_BUCKET_NAME` (not the video asset bucket) to allow
independent lifecycle policies and cost optimization
- **No new DB table**: Follows the same pattern as video uploads — S3 is the store of record,
`SignalFeed.last_capture_at` tracks liveness only
- **No authentication**: Matches existing `upload-video` pattern — internal operation routes are
network-restricted (VPC/private subnet only)
- **Camera name in S3 key**: Uses `SignalSource.name` for human-readable paths when available,
falls back to `camera_id`

## S3 Key Format

```
security/cameras/{account_id}/{project_id}/{camera_name}/images/{YYYY-MM-DD}/{filename}
```

- `camera_name`: resolved from `SignalSource.name` if available, otherwise `camera_id`
- `filename`: preserved as `YYYY-MM-DD_HH-MM-SS{ext}` when the upload filename matches
  `snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS{ext}` or the same basename; otherwise generated
  as `{HHMMSS}-{uuid8}{ext}` with a warning log
- `uuid8`: 8-char hex suffix prevents same-second collisions for generated fallback names
- `ext`: `.jpg`, `.jpeg`, or `.png`

## API Endpoint

```
POST /v1/operation/accounts/{account_id}/projects/{project_id}/cameras/{camera_id}/upload-photo
```

**Request:** `multipart/form-data` with field `photo` (UploadFile)

**Responses:**


| Status | Description                             |
| ------ | --------------------------------------- |
| 200    | Success — returns `{"url": "<s3_key>"}` |
| 400    | Invalid extension or missing filename   |
| 413    | File exceeds 10 MB                      |
| 500    | S3 upload failure                       |


**Validations:**

- Extensions: `.jpg`, `.jpeg`, `.png` only
- Max file size: 10 MB
- File pointer reset before upload (guards against partial reads)

## Implementation

### Files Changed


| File                                              | Change                                           |
| ------------------------------------------------- | ------------------------------------------------ |
| `api/routes/operation/_photo_upload.py`           | **New** — endpoint implementation                |
| `api/routes/operation/__init__.py`                | Route decorator + import                         |
| `api/schemas/operations/asset.py`                 | `AssetResponse` model (reused from video upload) |
| `conftest.py`                                     | Added `AWS_IMAGE_BUCKET_NAME` env var default    |
| `tests/api/routes/operation/test_photo_upload.py` | **New** — 12 test cases                          |


### Key Implementation Details

1. **S3 upload**: `boto3.client("s3").upload_fileobj()` via `run_in_threadpool` (async-safe)
2. **Camera lookup**: Best-effort — queries `SignalSource` by `camera_id` + `project_id` to get
  human-readable name. Failure doesn't block upload.
3. **Signal feed update**: Best-effort — updates `SignalFeed.last_capture_at` for the matched source.
  Uses the timestamp parsed from snapshot filenames when available; filenames without a parseable
  timestamp log a warning and fall back to upload time. Feed update failure doesn't block upload
  (logged and swallowed).
4. **File pointer**: `photo.file.seek(0)` before upload to prevent truncated objects.

### VM Side (camera_manager.py)

The `SnapshotCaptureThread` in the VM's `camera_manager.py`:

- Runs ffmpeg with `fps=1/15` filter to capture one JPEG every 15 seconds
- `_upload_loop` thread scans for `.jpg` files older than 5 seconds
- POSTs each file to the `upload-photo` endpoint for all configured API targets
- Deletes local file after successful upload to all targets
- Auto-restarts with exponential backoff on failure

## Test Coverage


| Test                                          | Verifies                                        |
| --------------------------------------------- | ----------------------------------------------- |
| `test_successful_upload`                      | Happy path: valid JPEG → 200 + S3 key returned  |
| `test_timestamp_filename_uses_capture_time_key` | Snapshot timestamp filename drives S3 key and capture time |
| `test_updates_signal_feed`                    | SignalFeed.last_capture_at updated after upload |
| `test_png_extension_accepted`                 | `.png` files accepted with correct content type |
| `test_unsupported_extension_rejected`         | `.gif`, `.bmp` etc. → 400                       |
| `test_missing_filename_rejected`              | No filename → 400                               |
| `test_oversized_file_rejected`                | >10 MB → 413                                    |
| `test_bucket_not_configured`                  | Missing env var → 500                           |
| `test_s3_client_error_raises_500`             | S3 ClientError → 500                            |
| `test_unexpected_s3_error_raises_500`         | Generic S3 error → 500                          |
| `test_camera_not_found_still_uploads`         | Camera lookup fails → upload still succeeds     |
| `test_camera_lookup_error_still_uploads`      | Camera lookup exception → upload still succeeds |
| `test_feed_update_failure_doesnt_fail_upload` | Feed update fails → upload still succeeds       |


## Potential Concerns

- **No auth on operation endpoints**: Existing pattern — network-restricted. Not in scope to change.
- **File in memory**: `photo.file.seek(0)` + `upload_fileobj` streams from SpooledTemporaryFile.
For files under 10 MB this is fine.
- **No deduplication**: Re-uploading same timestamp overwrites (UUID suffix makes this extremely
unlikely). Acceptable — idempotent behavior.
- **Camera name sanitization**: `source.name` is used directly in S3 key. S3 allows most characters
but names with `/` would create unexpected prefixes. Current camera names are simple slugs.

## Related

- Video upload endpoint: `api/routes/operation/_video_upload.py`
- Signal source/feed tables: `db/tables/signal_sources.py`, `db/tables/signal_feeds.py`
- VM camera manager: `Camera/camera_manager.py`
