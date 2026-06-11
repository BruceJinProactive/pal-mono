# Change Log

Chronological record of significant changes. Each entry links to the relevant doc.

---

## 2026-06-11

- **Guest menu board vision rule schema.** Added `guest_visiting_menu_board`
  to the `visionruletype` enum so menu-board monitoring rules can be
  persisted. Migration: `c2f4d8a9b1e3`.
- **Admin conversation order status filter.** `GET /accounts/{account_name}/conversations` now accepts `order_filter=all|paid|unpaid`, allowing the admin console to filter placed-order conversations by whether the latest stored order has a displayable order number.
- **Vision state-change event video URL.** `GET
  /accounts/{account_name}/state-change-events/{event_id}` now accepts
  `include_video` (default `false`) and returns nullable `video_url` when
  requested, using `event_metadata.video_url` or the video key derived from the
  event image minute. -> `docs/state/architecture.md`
- **Catering history count updates.** `PATCH /catering/requests/{request_id}` now accepts and persists `prior_catering_request_count` and `prior_order_count`, allowing internal admin edits to survive page reloads.

## 2026-06-10

- **Contract-to-account onboarding PRD.** Added a draft PRD for the account onboarding flow from verbal yes through DocuSign/order-form signing, ToS acceptance, Slack/Folk/Notion visibility, and FDE handoff. -> `docs/plans/onboarding/contract-account-tos-handoff-prd.md`
- **Admin conversation order filter.** `GET /accounts/{account_name}/conversations` now accepts `has_order` so the admin console can list only conversations with stored orders, or only conversations without stored orders, while preserving correct pagination totals.
- **Catering request financial history schema.** Added `catering_requests`
  columns for creation-time prior activity snapshots and nullable
  order/deposit value tracking. Migration: `b7f43f8aac6e`. ->
  `docs/records/2026-06-10-catering-request-financial-history-fields.md`
- **Catering partial-lead runtime adapters.** Repository DTOs, catering API
  schemas, service create/update/read paths, public detail responses, and agent
  catering persistence now accept nullable `event_date`,
  nullable `contact_phone_number`, and optional `contact_email`. Notification
  paths guard partial leads instead of inventing placeholder contact details. ->
  `docs/records/2026-06-08-catering-request-partial-lead-schema.md`
- **Catering request financial and history fields.** Added creation-time
  customer-history snapshots to `catering_requests` for prior same-account
  catering requests matched by requester phone or email, plus same-account
  prior order counts matched by phone, nullable estimated/confirmed order value,
  and deposit
  requirement/received value fields. The create path now populates history
  snapshots, and create/update APIs can set the monetary fields. Migration:
  `b7f43f8aac6e`. ->
  `docs/records/2026-06-10-catering-request-financial-history-fields.md`

---

## 2026-06-09

- **Camera video upload LLM flag.** `POST /v1/operation/accounts/{account_id}/projects/{project_id}/cameras/{camera_id}/upload-video` now accepts multipart `llm_analysis` (default `true`) and stores it as S3 object metadata while keeping the existing upload path.
- **Project subscription trial_end sync.** `PATCH /projects/{project_id}/subscriptions/{external_id}` now accepts `trial_end` for project-level trial adjustments, maps it to the local billing start date, exits existing trials when shortened into the past, retires the previous non-deleted project subscription version before inserting the replacement row, and syncs the trial end timestamp to Stripe before committing when the project subscription has a Stripe subscription ID.
- **Catering item list API plumbing.** Catering request APIs and persistence adapters now carry an optional `all_items` map keyed by item name, allowing item-level quantity, price, modifier, and special-note details to stay separate from broad `event_detail` notes.
- **Public catering confirmation details.** The unauthenticated catering request
  detail endpoint now includes `contact_phone_number` and project `address` as
  `store_address`, allowing confirmation pages to show requester phone numbers
  and pickup store locations while still withholding project IDs, contact
  assignment, idempotency keys, and internal timestamps. ->
  `docs/state/architecture.md`
- **Admin conversation order details.** Added an admin endpoint for fetching the latest stored order details for a conversation, using an explicit order projection that avoids loading problematic `orders.order_time` values while giving the admin console enough data for an order details modal.
- **Catering item list storage schema.** Added nullable `catering_requests.all_items` JSONB storage for structured catering item maps keyed by item name, keeping item-level modifiers, quantity, price, and special notes separate from freeform event notes. Migration: `f2b5c6a7d8e9`.
- **Vision rule metadata replacement.** `PATCH /accounts/{account_name}/vision-rules/{rule_id}` now replaces `rule_metadata` when the field is provided, allowing callers to delete old metadata keys by omitting them from the replacement object. -> `docs/state/architecture.md`
- **Vision snapshot observed-at timestamps.** Camera photo uploads now parse UTC capture time from `snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS.jpg` filenames, and Vision V2 observations use matching image-key timestamps for `observed_at` instead of backend processing time when available; non-matching filenames keep the old backend-time fallback and emit warnings. -> `docs/state/architecture.md`
- **Admin conversation order presence.** Admin conversation list/detail responses now distinguish displayable order numbers from order existence: real non-zero order IDs are returned as `order_number`, while conversations with placeholder order IDs still return `has_order=true` so the admin console can identify unpaid placed-order conversations without changing POS order persistence.

---

## 2026-06-08

- **Toast checkout session storage schema.** Added `toast_checkout_sessions` for UUID-backed Toast checkout links, including idempotency by payment external reference and status fields for async processing/delivery state. Migration: `8cf3a1b9e2d4`. -> `docs/records/2026-06-08-toast-checkout-session-schema.md`
- **Internal camera lookup skips unconfigured cameras.** `GET /internal/projects/{project_id}/signal-sources/camera` now returns `204 No Content` when a camera upload references a `camera_id` that is not configured as a signal source for the project, allowing processors to skip the media without logging a 404 as an unexpected backend error.
- **Catering partial-lead schema.** `catering_requests.event_date` and
  `contact_phone_number` are now nullable, and `contact_email` was added as a
  nullable column so incomplete catering inquiries can be tracked before all
  scheduling/contact details are known. This PR is schema-only; service/API
  adapters follow separately. Migration: `4caa090da0f5`. ->
  `docs/records/2026-06-08-catering-request-partial-lead-schema.md`
- **Admin conversation order numbers.** Admin conversation list/detail responses now include `order_number`, sourced from the latest displayable external `orders.order_id` for the conversation, so the admin console can match placed-order conversations to POS orders. -> `docs/log.md`
- **Tool-result cache dual-read validation.** Added cross-pod-style adapter coverage that writes with one Redis client and reads with another, plus message-service failure tests proving Redis read timeouts do not break non-streaming or streaming pal-agents responses during the dual-read rollout. -> `docs/plans/tool-result-elasticache-migration.md`

---

## 2026-06-07

- **Catering request activity timeline.** Added `catering_request_activities` as
  an append-only per-request timeline with typed actors/sources/activity types,
  JSONB metadata, actor details, timestamps, and lookup indexes. Runtime
  repository and service wiring now records request creation, request updates,
  and status changes; the project request list can embed activities for the
  catering workflow page when requested. Migration: `20cb36ab46c9`. ->
  `docs/records/2026-06-07-catering-request-activity-log.md`
- **Invitation links prefill passwords for pending Cognito users.** Team invites now reset and embed a fresh temporary password when the invited email already exists in Cognito with `FORCE_CHANGE_PASSWORD`, matching resend behavior so the admin console can prefill the password field from the invitation token. -> `docs/log.md`

---

## 2026-06-06

- **Admin ordering metrics API.** Added account-scoped ordering dashboard metrics for Admin Console, gated by ordering capability/integration detection. The API returns daily Total Order and Total Order Value from the existing Slack conversion metric source (`conversations_with_orders`, `total_subtotal`) and computes Order Accuracy from order conversations without tool-call errors. -> `api/schemas/admin/ordering_metrics.py`

---

## 2026-06-05

- **Selected-location subscription checkout.** Account subscription checkout now accepts an optional `project_ids` subset so the admin console can send only the locations selected for purchase; omitted `project_ids` keeps the existing all-attached-projects behavior, while empty or unknown selections fail before Stripe checkout is created. -> `docs/state/billing.md`
- **Message service tool-result cache reads.** `message_service` now reads `tool-results:v1:{conversation_id}` through `utils.cache.tool_result_cache.get_tool_results(...)` before `PalAgent.run(...)`, attaches non-empty results to `RuntimeContext.previous_tool_results`, and logs hit/miss counts while leaving pal-agents process-local fallback untouched on misses. -> `docs/plans/tool-result-elasticache-migration.md`

---

## 2026-06-04

- **Vision rule labels API.** Vision-rule API responses now include `label`, and PATCH updates can replace labels with a provided string list, including `[]` to clear them. -> `docs/state/architecture.md`
- **Vision rules grouped by label.** `GET /accounts/{account_name}/vision-rules` now includes `items_by_label`, where each rule appears under every label it carries and unlabeled rules appear under `no-labeld`. -> `docs/state/architecture.md`
- **Paginate state-change event list.** `GET /accounts/{account_name}/state-change-events` now accepts `page` plus `limit`, returns rows ordered by `observed_at` descending for that page, and reports `total` as the full filtered match count. -> `docs/state/architecture.md`
- **Admin conversation call-purpose filters use first-level purposes.** Conversation filter values now split historical comma-joined `Conversation.purpose` strings into canonical `CallPurpose` enum values, and filtering by a purpose matches conversations whose purpose list contains that selected token instead of requiring an exact whole-string match. -> `docs/log.md`
- **Message service tool-result cache writes.** `message_service` now schedules best-effort background writes for streaming and non-streaming `tool_call` payloads through `utils.cache.tool_result_cache.append_tool_result(...)`, keeping Redis details inside the cache adapter. -> `docs/plans/tool-result-elasticache-migration.md`
- **Tool-result cache per-family allowlists.** Strengthened the ElastiCache tool-result cache adapter so `build_cacheable_tool_result(...)` applies explicit Toast, Adora, and generic `cacheable_result` field allowlists before byte-limit checks while retaining recursive sensitive-key redaction. -> `docs/plans/tool-result-elasticache-migration.md`
- **Vision rule event durations.** State-transition rule workflows now persist `vision_rule_event.duration` as the elapsed minutes spent in the previous state before the trigger state, such as table `dirty` to `clean`; unresolved start times keep the `0.0` default. -> `docs/state/architecture.md`
- **Vision rule events list is uncapped.** Removed the `limit` query parameter from `GET /accounts/{account_name}/rule-events`; the endpoint now returns all rule events matching account, rule/entity, and time filters, and each response item includes `duration`. -> `docs/state/architecture.md`
- **Voice transfer reason classification.** Folded VSA-style transfer reason category and agent-fault analysis into the existing post-call LLM analytics pass so call purpose, end reason, language, satisfaction, and transfer reason are produced together.
- **Phone call transfer reason fields.** Added nullable `phone_calls.transfer_reason_category` and `phone_calls.transfer_agent_was_at_fault` columns for post-call transfer analytics. Migration: `d27a86f44484`.

## 2026-06-03

- **Add Pokeworks vision rule enum values.** Added `empty_tray`, `people_queued_up`, and `floor_cleanness` to the `visionruletype` enum so manage-app rule configuration can create those rule types. Migration: `d3b0731aa483`. -> `docs/state/architecture.md`
- **Tool-result ElastiCache adapter.** Added a best-effort async tool-result cache adapter that writes sanitized allowlisted tool results to `tool-results:v1:{conversation_id}` with `RPUSH`/`EXPIRE`, reads entries with `LRANGE`, drops malformed cache items, and emits structured logs/metrics without failing requests. -> `docs/plans/tool-result-elasticache-migration.md`
- **Add vision rule label and event duration columns.** Added `vision_rule.label` as an empty-default text-array column and `vision_rule_event.duration` as a non-null fixed-scale numeric duration in minutes with default `0.0`. Migration: `3b581347a98c`. -> `docs/state/architecture.md`
- **Vision entity current-state delete contract.** The per-entity current-state DELETE endpoint now returns 204 No Content and clears typed current-state metadata by definition type even when the stored state ID is malformed. -> `docs/state/architecture.md`

## 2026-06-02

- **Vision state-change events list is uncapped.** Removed the `limit` query parameter from `GET /accounts/{account_name}/state-change-events`; the endpoint now returns all events matching the account, project/entity, and time filters. The default time window remains the past 24 hours when `start` is omitted.
- **Shared Redis cache client config.** Added reusable pal-mono Redis/Valkey cache settings, Redis client factory, local env examples, Redis wait support, and docs clarifying Secrets Manager versus IAM auth for ElastiCache. -> `docs/plans/tool-result-elasticache.md`
- **Project delete MissingGreenlet guard.** Admin project deletion now snapshots project scalar fields before subscription, voice-config, or project delete commits can expire async ORM objects, preventing `greenlet_spawn has not been called` failures during delete cleanup. -> `docs/log.md`
- **Conversation caller identifier in admin responses.** Admin conversation list/detail responses now include a stable `sender_identifier` derived from the conversation user's channel identifiers, so voice calls with no user transcript can still display the caller number when the latest persisted message lacks sender metadata.
- **Public catering request details endpoint.** Added unauthenticated `GET /v1/catering/requests/{catering_request_id}/public` for guest-facing catering detail pages. The public response omits project IDs, phone numbers, contact assignment, idempotency keys, and timestamps while returning event details, fulfillment, party size, contact name, and status.
- **Expand vision rule workflows.** Added state-transition workflows for `table_touch`, `glove_usage`, `food_container_on_ground`, `manager_in_room`, and `staff_at_front_desk`, joining the existing `table_cleanness` and `table_occupied` workflows. -> `docs/state/architecture.md`

---

## 2026-06-01

- **Tool-result cache migration plan switched to ElastiCache.** Updated the existing tool-result migration plan to target AWS ElastiCache instead of DB-backed persistence, matching the ElastiCache implementation notes and covering sanitized result shape, TTL-only list retention, read/write flow, rollout, and testing. -> `docs/plans/tool-result-elasticache-migration.md`
- **[PAL-10984] Track typed current states on vision entities.** Vision entity state updates now maintain `metadata.current_states` keyed by state-definition type, emit one state-change event per changed type, and expose the parsed map on entity responses. Default entity creation initializes every default state type, observation parsing no longer treats a top-level `state` key as legacy without an explicit marker, and state-definition delete guards check both legacy columns and typed metadata. -> `docs/state/architecture.md`
- **[PAL-10949] Add state definition metadata columns and typed prompt grouping.** Added `definition_type` and `is_active` to `vision_entity_state_definition` so state definitions can be grouped by purpose and toggled active/inactive. Vision observation prompts now load only active state definitions and group options by `definition_type` so the LLM judges each active group separately. The existing text `criteria` column remains unchanged. Migration: `3742a24deea6`.
- **Add vision rule types.** Added `table_occupied`, `table_touch`, `glove_usage`, `food_container_on_ground`, `manager_in_room`, and `staff_at_front_desk` to the `visionruletype` enum for upcoming Chubby and Chica rule workflows. Migration: `11b2725caceb`.
- **Add table occupied vision rule workflow.** Added the first follow-on rule workflow: `table_occupied` creates a `vision_rule_event` when a `table` changes from `empty` to `occupied` in the `occupation` state-definition group. -> `docs/state/architecture.md`

---

## 2026-05-31

- **Order idempotent write schema.** Added nullable `orders.idempotency_key`, backfilled the newest canonical historical row per `(vendor, store_id, order_id)`, and added a unique partial index for non-null idempotency keys. -> `docs/records/2026-05-31-order-idempotent-writes.md`

---

## 2026-05-30

- **Catering customer SMS copy refresh.** Updated catering status SMS messages to use warmer customer-facing wording, include the requester name when available, explain confirmed/preparation/ready states, and make pickup/delivery and callback context clearer.

---

## 2026-05-29

- **Toast webhook menu update toggle.** Toast menu webhooks now respect `project_integration.config.auto_update_menu_on_webhook`, defaulting to enabled for existing stores and skipping menu refresh when explicitly disabled.

---

## 2026-05-28

- **Voice SLO metrics.** Added explicit OTel counters and duration histograms for the `Voice call close` and `Chat turn bridge` SLO boundaries, so Grafana/Mimir can distinguish true SLO success from HTTP 2xx, fallback, empty-output, and persistence-failure proxy signals. -> `docs/records/2026-05-28-voice-slo-metrics.md`

---

## 2026-05-27

- **Tool-result ElastiCache implementation notes.** Documented how shared cross-pod tool-result storage could be implemented with AWS ElastiCache, including app dependency, key shape, read/write paths, connection management, and rollout steps. -> `docs/plans/tool-result-elasticache.md`
- **[PAL-10801] Add default partition for vision rule events.** Added the missing `vision_rule_event_default` partition so matched rule events can be inserted when no date-specific `triggered_at` partition exists. This mirrors the existing `vision_state_change_event_default` fallback partition. -> `docs/state/architecture.md`
- **Auto-billing invoice flow doc.** Added a current-state walkthrough for the arrears billing invoice lifecycle: invoice draft creation, previous-draft finalization, analytics invoice email delivery, credit application, payment webhooks, unpaid balance accrual, and cancellation cleanup. -> `docs/state/auto-billing-invoice-flow.md`

---

## 2026-05-26

- **Vision v2 event generation voting/hysteresis plan.** Documented runtime last-N-frame voting and hysteresis for v2 vision event generation, plus the manual `pal-research` golden-labeling workflow used for evaluation. -> `docs/plans/golden-label-manage-app.md`

---

## 2026-05-25

- **Local Docker startup reliability.** Updated the OTel collector image from unavailable `otel/opentelemetry-collector-contrib:0.115.0` to published patch tag `0.115.1`, removed the obsolete Compose `version` field, and made `scripts/docker_build.sh` exit instead of printing success when `docker-compose up` fails.

---
## 2026-05-22

- **[PAL-10712 / PAL-10797] Process verification pipeline for voice eval.** Added the verifiable-process eval pipeline: `ProcessTrace` with HTTP and voice trace building, process evaluators for `tool_timing`, `param_collection`, and `output_use`, and the `ExpectedProcess` scenario schema. Voice traces preserve audio spans (`start_ms`, `end_ms`), speaker, and channel metadata so future S2S evals can judge tool timing, tool params, output use, and silence gaps without depending on transcription quality.
- **Catering request status lifecycle.** Documented the planned lifecycle `LEAD` -> `PROPOSAL` -> `CONFIRMED` -> `LOCKED` -> `IN_PREPARATION` -> `READY` -> `COMPLETED` -> `CLOSED` and exposed `COMPLETED` as a distinct `RequestStatus` value. `COMPLETED` is operational fulfillment; `CLOSED` is administrative closure. → `docs/state/architecture.md`

---

## 2026-05-21

- **[PAL-10722] Add CRUD API for vision rules and get/delete API for rule events.** Full CRUD endpoints for `vision_rule` at `/accounts/{account_name}/vision-rules`. List/get/delete endpoints for `vision_rule_event` at `/accounts/{account_name}/rule-events` served by the existing `vision_event_service`. New `vision_rule_service` handles rule business logic.

---

## 2026-05-20

- **[PAL-10714] Add vision_rule_event table.** New time-partitioned `vision_rule_event` table to record when a vision rule fires. Composite PK `(id, triggered_at)`, partitioned by RANGE on `triggered_at`. Links rule, entity, and triggering state change event. Indexes on `(rule_id, triggered_at)`, `(entity_id, triggered_at)`, and `triggered_at` for efficient time-range queries.
- **[PAL-10735] Include presigned frame_url in prompt API test events.** Added `frame_url` field to `TestEventInfo` schema so the configuration prompt endpoint (`GET /vision/camera-configs/{config_id}/prompt`) returns a presigned S3 URL for each test event's captured frame.

- **[PAL-10702] Add vision_rule table.** New `vision_rule` table scoped to projects for defining camera observation rules (e.g. table cleanness). Uses a PostgreSQL enum type (`visionruletype`) for the `type` column. Simplified the configuration prompt endpoint path from `/vision/accounts/{account_id}/projects/{project_id}/camera-configs/{config_id}/prompt` to `/vision/camera-configs/{config_id}/prompt`.

---

## 2026-05-19

- **[PAL-10669] Configuration prompt endpoint and test event metadata.** Added `GET /vision/accounts/{account_id}/projects/{project_id}/camera-configs/{config_id}/prompt` internal endpoint that returns the full system prompt, structured output schema, entity ROI hints, and test events grouped by `test_group`. Added `is_test` (bool) and `test_group` (str) fields to state-change event create/update/response schemas (stored in existing `event_metadata` JSONB). Added `PUT /accounts/{account_name}/state-change-events/{event_id}` endpoint for updating event metadata.

---

## 2026-05-13

- **[PAL-10592] Vision state change event CRUD API.** Added account-scoped GET/POST/DELETE endpoints for `vision_state_change_event` at `/accounts/{account_name}/state-change-events`. GET supports optional `project_id` and `entity_id` filters and defaults to the past 24 hours. New repository, service, and schema layers following existing vision entity patterns.
- **Arrears billing: finalize invoices at end of billing cycle.** Invoice drafts now stay open during the billing period (`auto_advance=False` set via `invoice.created` webhook). When the next period starts, the webhook finalizes and sends the previous period's draft (which by then includes metered usage from Stripe Meters). On subscription deletion, remaining drafts are also finalized. Accrual filter tightened to skip invoices with no `due_date`. Added `total_orders`, `order_total_dollars`, and `total_reservations` fields to `SendInvoiceEmailRequest` and passed through to Postmark template model for analytics emails.

---

## 2026-05-12

- **Mezeh routing eval scenarios.** Added `services/eval_service/scenarios/routing/mezeh.yaml` with five targeted scenarios for `call_transfer` and `send_support_email`: catering transfer, same-day order modification transfer, double-charge email, previous-day missing-item email, and post-email transfer request regression coverage.
- **[PAL-10536] Replace `camera_config_id` with `camera_id` in observation API.** The `POST /vision/observations` endpoint now accepts `camera_id` (signal source UUID) instead of `camera_config_id`. The service resolves the camera configuration internally via `get_by_signal_source(camera_id)`. Simplifies the caller contract — the Frame Processor Lambda only needs the camera ID. Response schemas (`GenerateObservationResponse`, `EntityObservation`) updated accordingly.
- **[PAL-10524] Billing metrics endpoint and template-aware invoice emails.** Added `GET /admin/accounts/{account_name}/billing/metrics` endpoint returning call count, avg duration, reservations, orders, and dollar value for a billing period. Response includes `template_variant` and `template_id` (Postmark) auto-selected based on activity (answering/ordering/reservation). Also added optional `template_id` field to `SendInvoiceEmailRequest` so the manage app can pass the correct template when sending invoices. Backwards-compatible — omitting `template_id` uses the default answering template. → `docs/records/2026-05-12-billing-metrics-endpoint.md`
- **[PAL-10526] Thread `criteria` column through state definition API and prompt builder.** The `criteria` field (added to `vision_entity_state_definition` in a prior migration) is now exposed end-to-end: data class, repository create/read, API schemas (create/update/response), service layer CRUD, and the vision observation prompt builder. The LLM system prompt now renders per-state criteria descriptions under each entity type so the model can make more informed state determinations.
- **Streaming SMS item recap context.** `/chat/completions` now collects `pal-agents` `sms_followup.payload.item_recap` during streaming and passes it into the existing URL SMS summarization prompt alongside the streamed caller text. `sms_followup` remains formatter context only: it is not persisted as `tool_calls`, does not trigger SMS without a streamed URL, and does not route through `SMSTool.send_order_summary`. → `docs/plans/2026-05-12-sms-followup-context-consumption-pr2.md`

---

## 2026-05-11

- **Eval tool-call argument checks for generic pal-tools.** Added generic subset argument matching in `services/eval_service/evaluators/tool_call_args.py` and registered it for `call_transfer` and `send_support_email`. Scenario authors can now specify only the expected fields they care about in `expected_tool_calls[*].args`; extra actual tool arguments are ignored while mismatches and missing nested fields still fail deterministically. → `docs/state/eval-platform.md`
- **Conversation deep-link account lookup endpoint.** Added `GET /conversations/{conversation_id}/account` endpoint that returns the `account_name` owning a given conversation. Used by the admin console to auto-switch accounts when a user opens a conversation deep-link (e.g., from Slack notifications) while viewing a different account. The endpoint verifies the authenticated user has `account.read` permission on the conversation's account before returning. Schema: `ConversationAccountLookupResponse` in `api/schemas/admin/conversation.py`.
- **Skip Stripe billing for eval calls.** Added `is_eval: bool = False` field to `VoiceEndCallRequest` schema. Updated `_should_track_call_usage` in the voice end-call handler to short-circuit with skip reason `"eval_call"` when the flag is set, preventing eval pipeline calls from generating Stripe meter events. Backwards-compatible — defaults to `False` so existing agent workers are unaffected until they opt in.
- **Onboarding: attach existing Cognito users instead of failing** (PAL-10487 phase 2). `admin_service.create_account_user` previously raised on `UsernameExistsException`, aborting `/onboarding` and blocking any email that already lived in the admin Cognito pool (even if only attached to a different account). It now falls through: look up the existing `sub` via `admin_get_user`, attach the user to the new account, and **skip** the welcome-with-temp-password email (existing users already have credentials). Idempotent when the user is already an active member of the target account. Split into three helpers (`_get_cognito_user_sub`, `_attach_user_to_account`, `_send_welcome_email`). 6 new unit tests. Phase 1 (frontend half) shipped in pal-manage-app PR #633. → `docs/records/2026-05-11-onboarding-existing-cognito-user.md`

---

## 2026-05-07

- **[PAL-10400] Wire observation output to entity state updates.** Extended `EntityObservation` schema with `camera_config_id` and `state_id` fields. The observation service now resolves detected state names to `state_definition.id` via a lookup map and writes `current_state_id` + `current_state_since` back to the entity record after each observation. Also passes `config.llm_prompt` as the `analysis_task` argument to `analyze_image`, enabling per-camera custom prompts.
- **Add `vision_state_change_event` table.** Partitioned table (`PARTITION BY RANGE (observed_at)`) for recording entity state transitions detected by the vision pipeline. Composite PK `(id, observed_at)`, indexed on `(entity_id, observed_at DESC)` and `(observed_at DESC)`. Columns: `entity_id`, `camera_config_id`, `previous_state_id`, `new_state_id`, `confidence`, `frame_s3_key`, `observed_at`, `metadata` (JSONB). Migration: `a680fe8fc678`.
- **Add `criteria` column to `vision_entity_state_definition`.** Nullable `VARCHAR(500)` column to describe what qualifies as each state (e.g., "No dishes or trash on the surface" for `clean`). Migration: `5ca029ff7265`.
- **[PAL-10382] Internal vision observation API endpoint.** Added `POST /internal/vision/observations` for generating entity state observations from camera frames. The endpoint accepts a camera config ID, optional S3 image key, and optional image file upload (for testing). The service layer (`services/vision_observation_service/`) loads camera configuration, retrieves assigned entities and state definitions, auto-builds a structured output JSON schema, and calls the configured LLM (Azure OpenAI or Google Gemini) via the existing `MonitoringLLMProvider` abstraction. Returns per-entity state + confidence scores. Schema: `api/schemas/operations/vision_observation.py`.

---

## 2026-05-06

- **Voice simulation parameters: run-level overrides + noise injection pipeline.** Added `VoiceOverridesRequest` schema on `RunEvalRequest` (`api/schemas/eval/requests.py`) allowing callers to override persona, speed, background_noise, noise_level_db, and noise_type at the run level — highest priority in the resolution chain (run override > scenario config > persona registry > defaults). Threaded `voice_overrides: dict[str, Any] | None` through the service layer (`_runner.py` → `_voice_eval_runner.py`). Wired `NoiseMixer` from `pal_agents.evals.voice.noise_mixer` into `SyntheticCaller._speak_turn`: when noise is enabled, each PCM audio frame is mixed with synthetic background noise (street/car/home profiles) before LiveKit publishing. Added frozen `NoiseConfig` dataclass to `_synthetic_caller.py` for typed noise settings. → `docs/plans/evals/voice-simulation-parameters-prd.md`
- **Record voice params in eval results metadata.** Added `voice_params: dict[str, Any] | None` field to `ConversationRecord` (`_evaluators.py`). `run_voice_scenario` now populates it with resolved settings (persona, speed, background_noise, noise_level_db, noise_type) after completing the call. `_run_one_scenario` writes `voice_params` into the `raw_output` JSONB column of `EvalResult` rows, enabling filtering and grouping eval results by voice conditions without schema migration. → `docs/plans/evals/voice-simulation-parameters-prd.md`

---

## 2026-05-05

- **Eval Langfuse trace boundary per scenario** (PAL-10344). Each scenario (test case) now produces its own Langfuse trace with all turns nested underneath. Root cause: `opentelemetry-instrument` auto-instruments FastAPI, and `asyncio.create_task(_run_eval_background(...))` snapshotted the originating request's OTel span context — all scenarios and turns silently shared that `trace_id`. Fix: new `services/eval_service/_tracing.py::scenario_trace_boundary` detaches the inherited OTel context (`otel_context.attach(Context())`) and opens an explicit "Eval Scenario" root observation, with `eval_run:<uuid>` / `scenario:<id>` tags for Langfuse filtering. Wired into `_worker` in `services/eval_service/_runner.py`. 6 new unit tests covering Langfuse attribute propagation + OTel context isolation (including exception paths and sibling scenarios). → `docs/records/2026-05-05-eval-langfuse-trace-boundary.md`

---

## 2026-05-01

- **Eval case-spec → scenario YAML converter + Sonny's BBQ scenarios** (PAL-10278). New `services/eval_service/scripts/convert_case_specs.py` converts pal-agents case-spec JSON (Toast ordering cases with item + selection trees) into pal-mono `EvalScenario` YAML: opening utterance + AI-driven goal turn with shared `HARD_RULES` / `DEFAULT_CUSTOMER`, optional `get_toast_item_details_v3` lookup, and a required `toast_takeout_create_order_v1` call carrying full `selection_paths`. Speech strings are cleaned of internal Toast codes (`(.32)`, `(1LB)`, `(MOD)`, etc.); raw labels are kept in tool payloads. YAML emits `|` block literals for multi-line fields via a `SafeDumper` subclass. 19 tests covering round-trip `EvalScenario` validation. Generated `services/eval_service/scenarios/ordering/sonnys_bbq.yaml` (5,288 lines, do not hand-edit). Transitional — forward-compatible with the in-flight `eval_scenarios` DB migration; the same converter can be reused by the future seed script. → `docs/records/2026-05-01-eval-case-spec-converter.md`

---

## 2026-04-29

- Add Vision Entity Type CRUD API (`/v1/operation/accounts/{account_id}/entity-types`) — repository, service, routes, schemas, OTel tracing, structured logging, 16 tests → `docs/records/2026-04-29-vision-entity-type-api.md`
- **Credit-funded subscriptions: `activate_subscription_without_payment_method()` + `create_subscription_direct()`** — New service functions for activating pending subscriptions via Stripe `send_invoice` collection method (no payment method required). Supports optional credit grants with idempotency keys, future-start-date trialing, and account coupon pass-through. Added `SubscriptionStatus.trialing` to `AccountSubscription.is_valid` so trialing subscriptions work with validity-gated flows (updates, invoice handling). → `docs/plans/billing/credit-funded-subscriptions-tech-design.md`
- **Credit-funded subscriptions: service functions + admin activate endpoint** — New service functions `activate_subscription_without_payment_method()` and `create_subscription_direct()` for activating pending subscriptions via Stripe `send_invoice` collection method (no payment method required). Supports optional credit grants with idempotency keys, future-start-date trialing, and account coupon pass-through. Added `SubscriptionStatus.trialing` to `AccountSubscription.is_valid` so trialing subscriptions work with validity-gated flows (updates, invoice handling). Wired up `POST /v1/admin/accounts/{account_name}/subscriptions/{external_id}/activate` admin endpoint with `ActivateSubscriptionRequest`/`ActivateSubscriptionResponse` schemas. → `docs/plans/billing/credit-funded-subscriptions-tech-design.md`
- **Eval runner: parallel scenarios within a run (all driver modes).** Replaced sequential `for scenario in scenarios:` loop in `services/eval_service/_runner.py` with a bounded `asyncio.gather` fan-out. `max_concurrency` is a request parameter on `RunEvalRequest` / `create_eval_run` (default 4), applied uniformly to text, direct, and voice modes — `run_voice_scenario` creates fully isolated per-scenario LiveKit resources (room, orchestrator, TTS engine, egress) with `finally:`-based cleanup, so voice concurrency is bounded by caller infra (worker pool, rate limits) rather than shared in-process state. Extracted `_run_one_scenario` so each worker owns its own `AsyncSessionLocal` (ADR-019); counter updates on the outer session are serialised via `asyncio.Lock`. → `docs/plans/conversation-eval/parallel-scenario-execution-plan.md`
- **Credit-funded subscriptions: service functions + admin activate endpoint + invoice.created webhook** — New service functions `activate_subscription_without_payment_method()` and `create_subscription_direct()` for activating pending subscriptions via Stripe `send_invoice` collection method (no payment method required). Supports optional credit grants with idempotency keys, future-start-date trialing, and account coupon pass-through. Added `SubscriptionStatus.trialing` to `AccountSubscription.is_valid` so trialing subscriptions work with validity-gated flows (updates, invoice handling). Wired up `POST /v1/admin/accounts/{account_name}/subscriptions/{external_id}/activate` admin endpoint with `ActivateSubscriptionRequest`/`ActivateSubscriptionResponse` schemas. Added `invoice.created` webhook handler with accrued balance logic: on new subscription invoice, sums unpaid past-due invoices, adds "Prior unpaid balance" line item to draft, and voids old invoices to prevent double-billing. → `docs/plans/billing/credit-funded-subscriptions-tech-design.md`
- Add `vision_camera_entity` DB table — many-to-many join between camera configurations and entities with optional `roi_hint` JSONB column; composite unique constraint on `(camera_config_id, entity_id)` → `docs/records/2026-04-29-vision-camera-entity-table.md`

## 2026-04-28

- **Eval `spec_modifier` — prevent real Toast/Adora order submission during eval runs.** Added optional `spec_modifier` hook to `message_service.get_chat_response_async`, applied after `construct_agent_spec`. New `services/eval_service/_safety.py::apply_eval_safety` is installed by default on `InProcessDriver`: forces `toast.submit_orders=False` and `adora.force_payment_link=True` (coerces Adora orders to payment-link flow, so nothing hits the POS). Zero production impact; production callers pass no modifier. → `docs/records/2026-04-28-eval-spec-modifier.md`

## 2026-04

### 2026-04-28
- Add `vision_entity_type` DB table for per-account vision entity type definitions (table, employee, food_tray, etc.); columns: `account_id` (indexed), `name`, `display_name`, `description`, `icon`, `is_active`; unique constraint on `(account_id, name)` → `docs/records/2026-04-28-vision-entity-type-table.md`
- Add `vision_entity_state_definition` DB table for per-entity-type state definitions (dirty, occupied, idle, etc.); columns: `entity_type_id` (indexed), `name`, `display_name`, `color`, `sort_order`, `is_default`; unique constraint on `(entity_type_id, name)` → `docs/records/2026-04-28-vision-entity-state-definition-table.md`
- Add `vision_entity` DB table for concrete per-project entity instances (Table 1, John, Tray A); columns: `project_id`, `entity_type_id`, `name`, `current_state_id`, `current_state_since`, `metadata` (JSONB), `is_active`; unique constraint on `(project_id, entity_type_id, name)` → `docs/records/2026-04-28-vision-entity-table.md`
- Add `vision_camera_configuration` DB table for per-camera LLM processing config (1:1 with signal_sources); columns: `signal_source_id` (unique), `project_id`, `name`, `llm_prompt`, `llm_provider`, `llm_model`, `processing_interval_seconds`, `reference_images` (JSONB), `enabled` → `docs/records/2026-04-28-vision-camera-configuration-table.md`

### 2026-04-27
- ADR drift fix: added [ADR-020](decisions/020-otel-langfuse-observability.md) documenting the target observability stack — Grafana LGTM (Loki/Tempo/Mimir) for Ops, Langfuse for LLM — and the in-progress Datadog removal. Updated [ADR-013](decisions/013-datadog-observability.md) to `Superseded by ADR-020`; added 2026-04 status notes to [ADR-018](decisions/018-vapi-to-livekit-migration.md) confirming code-level VAPI removal is complete; updated decisions index with inline status-change dates for `Superseded` / `Deprecated` rows.

### 2026-04-23
- Add `eval_scenarios` DB table to store eval scenario YAML files in the database, replacing filesystem-based scenario loading; columns: `project_id` (nullable — NULL for generic), `scenario_type`, `name`, `raw_yaml`; unique constraint on `(project_id, name)` → `docs/plans/eval-scenarios-db-migration.md`

### 2026-04-21
- Add `GET /v1/eval/runs` endpoint to list eval runs with optional `status`, `project_id`, and `limit` query params
- Add `POST /v1/eval/runs/{run_id}/cancel` endpoint to cancel running/pending eval runs; cancels the asyncio background task and marks DB row as failed
- Handle `asyncio.CancelledError` in eval background runner to avoid overwriting cancellation message
- Add `CancelEvalRunResponse` schema; cancel endpoint returns static success response instead of serializing expired ORM object
### 2026-04-20
- Remove `scenario_category` field from `POST /v1/eval/run` request; parameter was never used in runner — scenario selection is driven entirely by `project_map.json` lookup with generic fallback
- Remove `scenario_category` param from `load_scenarios()` in scenario loader

### 2026-04-17
- Add `scenario_files` field to `EvalRunResponse` schema; trigger endpoint resolves which YAML files will execute via `project_map.json` and returns them in the response so callers can confirm only the intended scenarios run
- Restructure eval scenarios: move per-client ordering YAML files into `scenarios/ordering/` directory; update `project_map.json` to map project IDs to file paths (e.g. `"ordering/friedmans.yaml"`) instead of directory names; runner uses `_resolve_scenario_files()` + `validate_scenarios_from_yaml()` to load specific files
- Default fallback when project not in `project_map.json` now loads only `scenarios/generic/` instead of all scenarios

### 2026-04-16
- Add optional `scenario_category` field to `POST /v1/eval/run` request; allows filtering eval scenarios by subdirectory (e.g. `"generic"`, `"ordering"`); threads through runner to `load_scenarios()`; omitting runs all scenarios (existing behavior)

### 2026-04-15
- [P2-D1c] Audio recording URI propagation: start LiveKit Room Composite Egress to record eval call audio to S3; add `recording_s3_bucket`/`recording_s3_region` to `VoiceEvalConfig`; add `_start_room_egress()`/`_stop_and_collect_egress()` helpers in eval runner; add `audio_recording_s3_uri` param to `VoiceResultCollector.collect()` (caller-supplied URI takes precedence over DB); enables E16 (STT accuracy) and E17b (audio quality) evaluators to access actual call recordings
- [P2-D1b] Voice transcript timestamp enrichment: persist conversation turns as Message records in `end_voice_call()` handler (previously ephemeral); update `VoiceResultCollector._extract_transcript()` to include `start_time`/`end_time`/`text`/`speaker` keys from message body; enables E14/E15/E17 evaluators to produce meaningful timestamp-based results

### 2026-04-14
- [PAL-9838] Add `GET /projects/{project_id}/monitoring/summary` endpoint returning per-tag health summaries (fail_rate, pass/fail/error counts) for dashboard location cards; single SQL with unnest/group-by; defaults to today; excludes skipped runs
- Add `tags` column (`ARRAY(Text)`, NOT NULL, default `{}`) to `monitoring_configs` table with GIN index for efficient tag-based filtering and grouping of monitoring configurations
- [P2-D1a] Add `SyntheticCaller` implementation in `services/eval_service/_synthetic_caller.py`; joins LiveKit room via livekit-rtc, publishes TTS audio for each eval turn, waits for agent responses via active-speaker detection; implements `SyntheticCallerFactory` protocol; update `run_voice_scenario` to create default `SyntheticCaller` when no `caller_factory` provided; embed `sip.callID` in participant token attributes via `_generate_caller_token()` so agent reads the eval call ID
- Change `SnapshotDiffResponse.prompt_diff` from raw unified diff string to structured `list[PromptChangeBlock]` with typed change blocks (`replace`, `delete`, `insert`), each containing correlated `added`/`removed` line lists

### 2026-04-13
- Add `POST /v1/snapshots:computeDiff` endpoint for computing unified text diff of system prompts and structured JSON diff of config between two fingerprinted snapshots
- [PAL-9811] Add `result`, `details`, `confidence` denormalized columns to `monitoring_runs` with indexes on `result` and `started_at DESC`; JSONB `evaluation_result` preserved for backward compatibility
- [P2-B1c] Add E16 STT accuracy / WER evaluator in `services/eval_service/evaluators/stt_accuracy.py`; compares primary STT transcript (Deepgram/Gladia) against Whisper reference transcription via word-level edit distance; includes S3 audio download, ffmpeg right-channel extraction, and OpenAI Whisper API integration; passes at ≤8% WER
- [P2-C1f] Wire voice eval into runner: add `_run_scenario_for_mode()` dispatcher in `_runner.py` that routes `driver: "voice"` to `run_voice_scenario`; add `"voice"` to `RunEvalRequest.driver` Literal; fix cleanup to be best-effort, add `asyncio.wait_for` timeout on caller factory
- [P2-B1d] Add E17 speech rate and E17b audio quality evaluators in `services/eval_service/evaluators/`; E17 computes per-turn WPM from transcript word count and duration, flags turns outside 120-180 WPM range; E17b estimates SNR from frame-level RMS and detects clipping (≥99% of 16-bit max); both metric-based, no LLM
- [P2-B1e] Add E18 speech fidelity LALM-as-Judge evaluator in `services/eval_service/evaluators/speech_fidelity.py`; uses DeepEval GEval with 5-level rubric (naturalness, pronunciation friendliness, pacing/brevity, conversational tone) scored by EVAL_MODEL (Claude Sonnet 4 via Bedrock); transcript-only, no audio model required
- [P2-C1f] Wire voice evaluators (E14-E18) into `evaluate_scenario()` orchestrator; extend `ConversationRecord` with `voice_transcript`, `turn_latencies_ms`, `audio_recording_s3_uri`, `is_voice` fields; update `VoiceEvalResult.to_conversation_record()` to populate voice metadata; voice evaluators are scheduled only when `is_voice=True` and required data is present; text-based eval paths unchanged
- Add `GET /v1/snapshots/{fingerprint}` endpoint for retrieving agent config snapshots by fingerprint — enables prompt traceability for chat and eval conversations

### 2026-04-08
- [P2-B1b] Add E14 Interruption and E15 Latency/silence metric-based evaluators in `services/eval_service/evaluators/`; E14 detects overlapping speech from transcript timestamps and explicit interruption events; E15 computes p50/p95 turn latency against SLA thresholds and detects awkward silence gaps (>3s)

### 2026-04-07
- [P2-A2] Extend `VoiceEndCallRequest` to accept per-turn call metrics from LiveKit agent worker; wire latency averages into existing PhoneCall columns; extract `compute_latency_averages` into `api/schemas/internal/voice_metrics.py` for testability
- Add `tool_call_records` table for persistent tool execution tracking per conversation ([record](records/2026-04-08-tool-call-records-table.md))
- Add `ToolCallRecordRepositoryAsync` with fire-and-forget recording and conversation query methods ([record](records/2026-04-08-tool-call-records-table.md))

### 2026-04-03
- [PAL-9574] Make `store_messaging_tool` transport-aware: auto-detect PizzaCloud via `sip_provider` field, route SMS through PizzaCloud broker

### 2026-04-02
- Add optional `pronunciation_dict_id` column to `voice_configs` table for per-project Cartesia pronunciation dictionaries
- Thread `pronunciation_dict_id` through admin voice config schemas and voice init response

## 2026-03

### 2026-03-31
- Add eval API routes and surface conversation fingerprints ([record](records/2026-03-31-eval-api-routes.md))

### 2026-03-30
- Integrate pal-agents DeepEval metrics (v0.2.210) into eval service — replace custom LLM judges (E2 menu_hallucination, E3 groundedness) with FaithfulnessMetric; add Responsive, VoiceAppropriate, TaskCompletion metrics; delete `_llm.py`
- Add Pydantic `field_validator` on voice config schemas to enforce allowed languages (`english`, `spanish`, `chinese`) at the API boundary
- Remove redundant manual language normalization from voice service and combined-language fail-fast from voice init
- Update priority field comments on `agent_capabilities` and `capability_actions` tables to clarify recency-based prompt positioning (comment-only, no schema change)

### 2026-03-28
- Add `eval_runs`, `eval_results`, `agent_config_snapshots` DB tables for eval platform ([record](records/2026-03-28-eval-platform-schema.md))
- Add `agent_fingerprint` and `prompt_fingerprint` columns to `conversations` table for agent version tracking ([record](records/2026-03-28-eval-platform-schema.md))

### 2026-03-26
- Add CapabilityAction resource type to change tracking enum ([record](records/2026-03-26-capability-action-change-tracking.md))
- Remove checklist service, routes, schemas, repository, and auth references — replaced by routine system ([record](records/2026-03-26-remove-checklist-service.md))
- Drop `checklists`, `checkpoints`, `checkpoint_runs` DB tables and remove table models ([record](records/2026-03-26-remove-checklist-service.md))

### 2026-03-25
- Deprecate old call transfer: remove `transfer_phone_number` from project admin schemas, delete `livekit_transfer_tool`, and drop deprecated transfer fields from agent config

### 2026-03-24
- Add daily catering inquiry reminder: internal endpoint `POST /internal/catering/inquiry-reminders` sends one SMS per project for INQUIRY requests exactly 2 days old whose event hasn't passed
- Remove outdated VAPI comments and references to deleted code paths (VAPI migration cleanup)
- Remove unused VAPI AssistantConfig and related dead code from number service (VAPI migration cleanup)
- Update database field comments to remove VAPI-specific language (VAPI migration cleanup)
- Remove legacy `released_from_vapi` field from ReleaseNumberResponse API schema (VAPI migration cleanup)

### 2026-03-21
- Restructure pal-skills submodule: mount at `.pal-skills` with sparse checkout (`.claude/skills/` only), symlink `.claude/skills` → `.pal-skills/.claude/skills`, add submodule init to `scripts/install.sh`

### 2026-03-20
- Remove the Adora raw-config overlay and document ProjectIntegration as the source of truth for Adora spec data → `docs/memory/long-term.md`

### 2026-03-19
- Clarify memory doc guidance for auth defaults, ADR-007 migration state, short-term section structure, and active-work curation → `docs/memory/long-term.md`, `docs/memory/short-term.md`, `docs/README.md`


### 2026-03-17
- Fix chat streaming async session ownership to prevent non-checked-in connection warnings → `docs/records/2026-03-17-chat-stream-session-lifecycle.md`

### 2026-03-03
- Fix the Async Issue (@BruceJinProactive, #3612)
- Refactor end_voice_call to simplify transaction handling and create p (@BruceJinProactive, #3611)
- Refactor end_voice_call to use a new session for phone call record cr (@BruceJinProactive, #3610)
- Ensure session commit and rollback in end_voice_call and phone call c (@BruceJinProactive, #3609)
- Fix save functionality by ensuring session commit and rollback in Pho (@BruceJinProactive, #3608)
- Enhance end_voice_call function to extract call analytics, update con (@BruceJinProactive, #3596)
- Add repository tests and fix 10 discovered bugs (@xiangkangjw, #3605)

### 2026-03-02
- Add pal agents adora as project integration (@graydonpower-dev, #3602)
- Add api channel to customer_phone population in non-streaming flow (@ronald-palona, #3601)
- Updating Filler Words (@jeffrey-weisinger, #3561)
- Update pal-agents version (@ronald-palona, #3600)
- Fix routine sorting & missed status detection (@teresatian-cell, #3599)
- Publish ConversationEvaluationRequested event from LiveKit end-of-call (@aidan-palona, #3598)
- Add mcp dependency for MCP server support (@xiangkangjw, #3597)
- Symlink .agents/skills to submodule, add changelog-updater skill (@xiangkangjw, #3595)
- Docs: reorganize documentation and add comprehensive change log (@xiangkangjw, #3594)
- Docs: add ADRs and VAPI-to-LiveKit migration decision (@xiangkangjw, #3593)
- Feat: add read-only MCP server for database exploration (@xiangkangjw, #3591)

### 2026-03-01
- Docs: reorganize documentation into tool-agnostic knowledge management system (@xiangkangjw, #3592)
- Docs: update architecture.md to reflect current codebase state (@xiangkangjw, #3590)
- Update model spec creation for priority (@crooksjeff, #3589)
- Add CI check to enforce tests in top-level tests directory (@xiangkangjw, #3587)
- Add 24 hour cache, priority api toggle (@crooksjeff, #3588)
- Use monkeypatch fixture to enforce test credentials deterministically (@xiangkangjw, #3586)
- Consolidate all tests into top-level tests directory (@xiangkangjw, #3570)
- Tool result for adora includes item recap (@crooksjeff, #3585)
- Bump pal-agents (@s-wang-la, #3584)

## 2026-02

### 2026-02-28
- Enable pal-agent filler and clean up the dangling ones (@s-wang-la, #3579)
- Bump pal-agent version (@s-wang-la, #3578)
- Add TTS context and remove bullet formatting from communication style (@andrewhcli, #3577)
- Pal agents led tool filler (@crooksjeff, #3576)

### 2026-02-27
- Updated pal agents to return direct to user on tool success (@crooksjeff, #3575)
- Update pal-agents version (@ronald-palona, #3574)
- Query history up to 100 (@crooksjeff, #3573)
- Fix duplicate pending executions on schedule time update (@teresatian-cell, #3572)
- Fix communication style template for voice agents (@andrewhcli, #3558)
- Bump pal agents. Instance bearer cache, httpx client reuse across tool (@crooksjeff, #3569)
- Fix LLMObs.annotate() failures in detached threads and async tasks (@xiangkangjw, #3568)
- Fix double text links (@s-wang-la, #3566)
- Fix text message sender (@s-wang-la, #3565)

### 2026-02-26
- Logging to investigate text jitter (@s-wang-la, #3564)
- Fix type error in video frames count tag assignment (@xiangkangjw, #3563)
- Fix: upgrade ddtrace 3.11.0 → 4.5.0 to fix intermittent streaming NoneType error (@xiangkangjw, #3562)
- Bump pal agents, remove session id chaining for ressponses api (@crooksjeff, #3560)
- Bump for delivery fix (@crooksjeff, #3556)
- Add LLM call analytics extraction and conversation formatting functions (@BruceJinProactive, #3555)
- Bump pal-agents to v0.2.87 (@crooksjeff, #3554)

### 2026-02-25
- Add debug logging for LiveKit transfer tool lk_api injection (@xiangkangjw, #3553)
- Remove vapi_tool → livekit_transfer_tool auto-swap (@xiangkangjw, #3551)
- Add voice provider reference docs for STT/TTS (@ronald-palona, #3548)
- Bump pal-agents to v0.2.82 (@xiangkangjw, #3550)
- Update VoiceEndCallRequest to use float for duration_seconds and log (@BruceJinProactive, #3549)
- Implement end call endpoint and request schema for LiveKit voice calls (@BruceJinProactive, #3547)
- Add tests for _build_tool_specs debug logging (@xiangkangjw, #3546)
- Add debug logging for tool loading/registration in agent_service (@xiangkangjw, #3545)
- Suppress agno library INFO logs to reduce noise (@xiangkangjw, #3503)
- Upgrade pal-agents to v0.2.74 and pal-tools to v0.1.13 (@xiangkangjw, #3544)
- Adora V3 Coupon - Extract coupon_data from raw_config (@Tim-Yang-YTY, #3539)

### 2026-02-24
- Cleanup unused logs and update to latest realtime model. (@s-wang-la, #3540)
- Add room_name and participant_identity to RuntimeContext (@xiangkangjw, #3543)
- Upgrade pal-tools to v0.1.12 and pal-agents to v0.2.62 (@xiangkangjw, #3542)
- Add pronunciation replacements to LiveKit voice init API (@xiangkangjw, #3538)
- Add pronunciation guideline (@s-wang-la, #3537)
- Add livekit_tool to pal-agents tool spec allowlist (@xiangkangjw, #3536)
- Fixed how feedback grabs display name (@kellyguan-create, #3535)
- Add LiveKit tool support (@xiangkangjw, #3534)
- TOS Version API Changes (@kellyguan-create, #3529)

### 2026-02-23
- Normalize phone numbers to E.164 and preserve destination_number on auto-swap (@xiangkangjw, #3533)
- Remove redundant monitoring service conftest (@xiangkangjw, #3466)
- Update catering request status values (@graydonpower-dev, #3532)
- DB Change: Add catering request statuses (@graydonpower-dev, #3531)
- Fix: improve conversation retrieval and analytics saving logic in ses (@BruceJinProactive, #3530)
- Support destination_number shorthand in LiveKitTransferTool (@xiangkangjw, #3528)
- Only enable LLMobs for non testing requests (@akshaybhatia-ops, #3325)
- Fix: adding capture last url (@BruceJinProactive, #3527)
- Logic to tos_acceptance (@kellyguan-create, #3363)
- Add capture URL handling to signal source and feed management (@BruceJinProactive, #3526)
- Fixed the polling to progress more seamlessly (@kellyguan-create, #3525)
- Added status endpoint for menu uploader and updated upload_menu (@kellyguan-create, #3523)
- Add LiveKit transfer gap support with auto-swap and context injection (@xiangkangjw, #3524)

### 2026-02-22
- Add Notion task linking validation for pull requests (@xiangkangjw, #3522)
- Add LiveKit cold transfer support with SIP REFER (@xiangkangjw, #3521)
- Added the call_forwarding_setup_completed field to all necessary for project schema (@kellyguan-create, #3520)
- Added call_forwarding_setup_completed field and default set to false (@kellyguan-create, #3519)
- Test to see if stable index and uuid affects buffering (@crooksjeff, #3518)
- Weight ids come from store menu (@crooksjeff, #3517)

### 2026-02-21
- Fix greenlet_spawn error in LiveKit voice init Step 6 (@xiangkangjw, #3516)
- Add per-step debug logging to LiveKit voice init endpoint (@xiangkangjw, #3515)
- Add LiveKit voice init internal endpoint with tests (@xiangkangjw, #3514)
- Add livekit-plugins-openai dependency (@xiangkangjw, #3512)
- Add .omc/ to gitignore (@xiangkangjw, #3508)
- Add incremental coverage check to CI workflow (@xiangkangjw, #3506)
- Fix alphabetical ordering of diff-cover in pyproject.toml (@xiangkangjw, #3507)
- Add diff-cover dependency for incremental coverage (@xiangkangjw, #3505)
- Add voice_provider support to purchase endpoint (@xiangkangjw, #3504)

### 2026-02-20
- Suppress noisy multipart parser debug logs (@xiangkangjw, #3501)
- Remove S3 upload path logging from video upload endpoint (@xiangkangjw, #3502)
- Replace request logging with StatsD metrics in middleware (@xiangkangjw, #3500)
- Suppress noisy library INFO logs — ~2.2M fewer logs/4h (Phase 3) (@xiangkangjw, #3499)
- Remove unnecessary log statements (@xiangkangjw, #3496)
- Add last_capture_url field to signal_feeds table (@BruceJinProactive, #3495)
- Remove noisy debug logs (Phase 2) — ~250K fewer logs/4h (@xiangkangjw, #3498)
- Fix pytest-coverage-comment exceeding GitHub character limit (@xiangkangjw, #3497)
- Add test coverage CI workflow with PR comments (@xiangkangjw, #3494)
- Add pytest and coverage configuration (@xiangkangjw, #3493)
- Optimize logging: reduce noise, add trace correlation and request middleware (@xiangkangjw, #3490)
- Add media type field to monitoring LLM token usage logs (@aidan-palona, #3488)
- Changed default for postmark (@kellyguan-create, #3491)

### 2026-02-18
- Add LiveKit SIP dual-stack voice provisioning with trunk_sid routing (@xiangkangjw, #3487)
- Add LiveKit SIP dual-stack voice provisioning for phone numbers (@xiangkangjw, #3486)
- Replace kelvin with jeff.crooks in CODEOWNERS (@xiangkangjw, #3482)
- Handle cancelled error in streaming (@ronald-palona, #3485)

### 2026-02-17
- Add LiveKit dependencies for real-time voice AI (@xiangkangjw, #3481)
- Add LiveKit migration planning docs (@xiangkangjw, #3479)
- Fix pyright error for google-genai namespace package imports (@xiangkangjw, #3483)
- Update adora tool to have process order right after validate, also al (@crooksjeff, #3480)
- Handle cancelled error in streaming (@ronald-palona, #3478)

### 2026-02-16
- Update tool desc (@crooksjeff, #3477)

### 2026-02-15
- Add CI check to enforce dependency changes in separate PRs (@xiangkangjw, #3476)
- Fix video frame extraction only extracting 1 frame (@xiangkangjw, #3475)

### 2026-02-14
- Isolate monitoring LLM traces from voice agent traces (@xiangkangjw, #3474)
- Adora provider prototype (@crooksjeff, #3473)

### 2026-02-13
- Enable testing of Adora_v2 api calls (@ronald-palona, #3471)
- Fixed Voice config for speech rate (@kellyguan-create, #3472)
- Filter out executions from inactive routines (@teresatian-cell, #3470)
- Added speed to voice config (@kellyguan-create, #3469)
- Fix twilio syntax (@s-wang-la, #3468)
- Realtime logging (@s-wang-la, #3467)

### 2026-02-12
- Remove eager imports from services/__init__.py and improve monitoring service code quality (@xiangkangjw, #3465)
- Bump pal-agent to 0.2.56 (@xiangkangjw, #3464)
- Fix config format (@s-wang-la, #3463)
- Add video monitoring support and comprehensive test suite (@xiangkangjw, #3462)
- Update realtime api params (@s-wang-la, #3461)
- Add missing paramters (@s-wang-la, #3460)
- Fix api parameters and audio format (@s-wang-la, #3459)
- Replace toast partner_added event logger.info with logger.debug (@TomYang-TZ, #3457)
- Refactor realtime path (@s-wang-la, #3455)
- Add model name to monitoring/checkpoint LLM logs and update time window terminology (@aidan-palona, #3456)

### 2026-02-11
- Fix realtime api issue (@s-wang-la, #3454)
- Patch dd (@crooksjeff, #3450)
- Add pal-skills submodule for shared Claude skills (@xiangkangjw, #3404)
- Update audio format (@s-wang-la, #3453)
- Add debug log for realtime (@s-wang-la, #3452)
- Fix greenlet (@BruceJinProactive, #3451)
- Add logs to debug (@s-wang-la, #3449)
- Fix: Greenlet issue (@BruceJinProactive, #3448)
- Refactor subscription request handler to extract stripe_customer_id a (@BruceJinProactive, #3447)
- Fix lazy loading issues in subscription request handler by extracting (@BruceJinProactive, #3446)
- Add subscription command handling and update related documentation (@BruceJinProactive, #3442)
- Patch dd (@crooksjeff, #3440)
- Add model name to checkpoint LLM token logs and improve time window enforcement (@aidan-palona, #3441)
- Dep bump + agents sdk context handling (@crooksjeff, #3434)
- Refactor camera account handling and improve response formatting in S (@BruceJinProactive, #3439)
- Fix DB query (@s-wang-la, #3438)

### 2026-02-10
- Test realtime model (@s-wang-la, #3431)
- Lower voiceSeconds from 0.4 to 0.3 to make it easier to interrupt agents (@TomYang-TZ, #3436)
- Add minitable default url (@s-wang-la, #3435)
- Fix: update active threshold calculation to use timezone-aware datetime (@BruceJinProactive, #3433)
- Fix: camera checker (@BruceJinProactive, #3432)
- Add help command and Home Tab handling to Slack bot (@BruceJinProactive, #3430)
- Revert openrouter (@crooksjeff, #3429)
- Stopasync iteration error (@crooksjeff, #3428)
- Add event publishing for routine scheduling update (@teresatian-cell, #3425)

### 2026-02-09
- Use openrouter now in pal-agents (@crooksjeff, #3427)
- Fix onboarding migration downgrade to drop enum type (@TomYang-TZ, #3420)
- Added bearer token into generic api (@crooksjeff, #3426)
- Fix migration problem with toms (@kellyguan-create, #3423)
- Add internal API for routine execution management (@BruceJinProactive, #3421)
- Changed backfill Kelvin email in lat (@MyroslavVozniak, #3422)
- Tom/toast webhook/partner added db insertion (@TomYang-TZ, #3419)
- Disable memory toggle (@kellyguan-create, #3417)
- Create OnboardingWebhookEvent table for tracking integration webhooks (@TomYang-TZ, #3418)
- Made backfill owners authenticate_user (@MyroslavVozniak, #3416)
- Revert "initial" (@MyroslavVozniak, #3415)
- Made backfill owners context read (@MyroslavVozniak, #3413)

### 2026-02-07
- Dd tracing change for debug (@crooksjeff, #3412)
- Cerebrus to test ttft on voice (@crooksjeff, #3411)
- Add and test customize params (@s-wang-la, #3410)

### 2026-02-06
- Update logs for ws (@s-wang-la, #3409)
- Fix ws url (@s-wang-la, #3408)
- Add log to understand streaming (@s-wang-la, #3407)
- Add webhook from twilio (@s-wang-la, #3405)
- Add language guideline (@s-wang-la, #3406)
- Notify caller when catering request is recorded (@graydonpower-dev, #3403)
- Remove unusable reservation list api doc (@s-wang-la, #3402)
- Fixed slack bot logic for feedback commands (@kellyguan-create, #3401)
- Feedback command on slack filter (@kellyguan-create, #3400)
- Feedback commands on Slack uses Notion DB only now (@kellyguan-create, #3390)

### 2026-02-05
- Bumped pal agents to support generic api injection (@crooksjeff, #3399)
- Model s is now direct openai gpt 5 mini (@crooksjeff, #3397)
- Reservation prompt (@s-wang-la, #3396)
- Bump pal-agents to v0.2.40 (@crooksjeff, #3393)
- Default missing channel (@s-wang-la, #3394)
- Revert "Revert "add stopSpeakingPlan configuration to all VAPI assistants"" (@TomYang-TZ, #3395)
- Changed pal agents model size, xs 5 nano, s 4o, m 5.2 no thinking, l (@crooksjeff, #3389)
- Add 8-mile radius fallback for Toast address validation when polygon unavailable (@TomYang-TZ, #3385)
- Fix: Request (@BruceJinProactive, #3387)
- Backfill the ownerless accounts (@MyroslavVozniak, #3386)
- Added Feedback - for all companies feedback (@kellyguan-create, #3384)
- Fix: handle None metadata in message_body to prevent AttributeError (@xiangkangjw, #3383)
- Add model name to monitoring LLM token usage logs (@aidan-palona, #3382)
- Sync `sonic-3 generationConfig.speed` with `voice_config.speech_rate` (@TomYang-TZ, #3381)

### 2026-02-04
- Add minitable api docs (@s-wang-la, #3380)
- Update pal agents to fix generic api schema, auth reformat (@crooksjeff, #3379)
- Debug vapi latency logs (@ronald-palona, #3378)
- Create Slackbot call to fetch tickets per client for each status type (@kellyguan-create, #3377)
- Debug vapi latency logs (@ronald-palona, #3375)
- Use add_message_to_conversation using the convo id instead of lookup, (@crooksjeff, #3374)
- Fixed to FeedbackID for conversation link (@kellyguan-create, #3373)
- Added challenge parameter for slack events (@kellyguan-create, #3372)
- Debug vapi latency logs (@ronald-palona, #3371)
- Enable accent localization to improve accent quality for sonic-3 (@TomYang-TZ, #3370)
- Added /events endpoint to slack integrations (@kellyguan-create, #3369)
- Fix video upload logging: rename 'filename' to 'video_filename' (@xiangkangjw, #3367)

### 2026-02-03
- Add filler words for long wait response (@s-wang-la, #3368)
- Add ws port (@s-wang-la, #3365)
- Move config to project raw config, add model, pal-agents, and generic (@crooksjeff, #3366)
- Fix: Improve effciency (@BruceJinProactive, #3364)
- Fix(toast): prevent substring matching in stock webhook item names (@TomYang-TZ, #3362)
- Add monitoring time window feature for configurable monitoring hours (@aidan-palona, #3358)
- Feat(api): add video upload endpoint for camera recordings (@xiangkangjw, #3361)
- Added slack command feedback to query unresolved client specific feedback (@kellyguan-create, #3360)
- Adding tos_acceptance table (@kellyguan-create, #3328)
- Debug vapi latency logs (@ronald-palona, #3359)
- Debug vapi latency logs (@ronald-palona, #3357)
- Adding Postmark emails to feedback flow (@kellyguan-create, #3356)
- Remove Friedman's (@ronald-palona, #3355)
- Debug vapi latency logs (@ronald-palona, #3354)
- Debug vapi latency logs (@ronald-palona, #3350)
- Feat(vapi): support languageGroups with voice/transcriber config from frontend (@TomYang-TZ, #3347)

### 2026-02-02
- Update reservation prompt (@s-wang-la, #3353)
- Add time range (@BruceJinProactive, #3351)
- Update reservation prompt (@s-wang-la, #3352)
- Modified self onboarding schema (@MyroslavVozniak, #3348)
- Add business hours filtering for monitoring image processing (@aidan-palona, #3312)

### 2026-02-01
- Prompt V2: Update ordering.yaml file to include payment link instructions in Checkout flow (@Tim-Yang-YTY, #3344)
- Update reservation default prompt (@s-wang-la, #3343)

## 2026-01

### 2026-01-31
- Update minitable docstring and return string in error case (@s-wang-la, #3342)

### 2026-01-30
- Verbosity low for nano (@crooksjeff, #3341)
- Bump pal agents to reflect infra changes (@crooksjeff, #3340)
- Add staff role with project-level access (@teresatian-cell, #3338)
- Bump pal agents to avoid lazy imports (@crooksjeff, #3339)
- Add token usage logging for checkpoint service LLM (@aidan-palona, #3337)
- Feedback - change convo link to link to prd (@kellyguan-create, #3329)
- Bump pal-agents to use gpt5 nano/mini in prd, allow comida to use mod (@crooksjeff, #3336)

### 2026-01-29
- Remove migration files from PRs #3277 and #3284 (@TomYang-TZ, #3335)
- Fix the broken streaming mode (@s-wang-la, #3332)
- Added trial_end and invoice_incoming notice webhook handlers (@MyroslavVozniak, #3331)
- Removed proration when switching plans (@MyroslavVozniak, #3330)
- Fix migration file dependencies to create linear chain (@TomYang-TZ, #3324)

### 2026-01-28
- Add performance indexes on conversations table (@xiangkangjw, #3277)
- Added owners email as default norification preference (@MyroslavVozniak, #3320)
- Revert "AdoraV2: Webhook for orderThreshold handling via AdminConsole" (@Tim-Yang-YTY, #3317)
- Slack now mentions FDE (@kellyguan-create, #3316)
- Add performance indexes on orders table (@xiangkangjw, #3284)
- Added Assigned FDE to Slack Bot (@kellyguan-create, #3315)
- Fix : Update formatting (@BruceJinProactive, #3314)

### 2026-01-27
- Fix : Update the notion user id (@BruceJinProactive, #3313)
- Feat : Create Notion page (@BruceJinProactive, #3311)
- Added allow multiple account for same user signup (@MyroslavVozniak, #3310)
- Hardcoded Notion Table ID and updated account_name relation with Notion Client Master Database (@kellyguan-create, #3308)
- Add token usage logging for monitoring LLM providers (@aidan-palona, #3309)
- Change adora menu updater to work with adora v2 (@graydonpower-dev, #3307)
- Integrated with Notion Client Master Database (@kellyguan-create, #3306)
- Fix : Slack Interaction (@BruceJinProactive, #3305)
- Added camera alert logging (@MyroslavVozniak, #3303)
- Feat Add interaction (@BruceJinProactive, #3304)
- AdoraV2: Webhook for orderThreshold handling via AdminConsole (@Tim-Yang-YTY, #3293)
- Feat [Self Onboarding]: Send Notification after self-onboarding (@BruceJinProactive, #3300)
- Add new account to use new framework (@ronald-palona, #3298)

### 2026-01-26
- Revert Add staff role (@s-wang-la, #3297)
- Query size (@s-wang-la, #3296)
- Fix: timezone-aware date filtering for routine executions (@teresatian-cell, #3294)
- Enlarge the query size (@s-wang-la, #3295)
- Feat: add staff role (@teresatian-cell, #3267)
- Allow partial updates for project integrations (@graydonpower-dev, #3292)
- Add project_ids column to UserInvitation table (@teresatian-cell, #3282)
- Feat: add delivery to call analysis prompt (service) (@andrewhcli, #3289)
- Feat: add delivery to CallPurpose enum (schema) (@andrewhcli, #3288)
- Propagate only negative feedback (@kellyguan-create, #3291)
- Add store_id parameter from store identifier column (@graydonpower-dev, #3290)
- Feedback Integration - Use AWS key (@kellyguan-create, #3287)
- Cleaned up feedback integration (@kellyguan-create, #3285)

### 2026-01-23
- Default toast tool index_name attribute to 'agents' (@TomYang-TZ, #3283)
- Optimize get_distinct_filter_values to use single query (@xiangkangjw, #3278)
- Feedback Integration - disable PostMark and mapping channels (@kellyguan-create, #3281)
- Raw config priority for tools over project integrations (@graydonpower-dev, #3280)

### 2026-01-22
- Fix default index_name to 'agents' when not found in config (@TomYang-TZ, #3276)
- AdoraV2: Force payment link for orders (@Tim-Yang-YTY, #3275)
- Change Toast default hosted checkout iframe endpoint (@TomYang-TZ, #3274)
- Add action default value (@s-wang-la, #3273)
- Added proactiveailab.com to bcc emails (@MyroslavVozniak, #3272)
- Add toast ordering (@s-wang-la, #3271)
- Update general prompt and add transfer prompt (@s-wang-la, #3270)
- Added bcc to notifications@proactiveailab.com for all customer emails (@MyroslavVozniak, #3269)
- Fix billing email price inconsistency (@MyroslavVozniak, #3268)
- Feat:[Routine Execution] Adding AI Details in response (@BruceJinProactive, #3266)
- Integrating Postmark to Feedback pipeline (@kellyguan-create, #3264)
- Fixed billing cycle parsing (@MyroslavVozniak, #3265)
- Fixed Stripe billing cycle retrieval mechanism (@MyroslavVozniak, #3263)

### 2026-01-21
- Add enabled support (@s-wang-la, #3262)
- Add enabled column to action (@s-wang-la, #3261)
- Ensure each Toast customer email is unique by including the customer’s phone number (@TomYang-TZ, #3258)
- Feedback Slack API Key (@kellyguan-create, #3260)
- Fix Notion Key retrieval from os to aws (@kellyguan-create, #3259)
- Remove transfer destination fallbacks (@ronald-palona, #3256)
- Fixed to fetch server secrets (@kellyguan-create, #3257)
- Fix: added notion-client to uv.lock file (@kellyguan-create, #3255)
- Remove trailing backslash from vapi api endpoint (@TomYang-TZ, #3253)
- Feat:[Routine Review] Returning the real name instead of uuid in resp (@BruceJinProactive, #3252)
- Feedback Channel - Slack, Notion, and Postmark Integration (@kellyguan-create, #3245)
- Fix: [Monitoring LLM] disabled DD trace for monitoring (@BruceJinProactive, #3251)
- Stripe webhook sync improvements (@MyroslavVozniak, #3250)
- Fix race condition in Toast stock webhook by using populate_existing() (@TomYang-TZ, #3248)
- Enable db transfer destination (@ronald-palona, #3247)
- Fixed subscription related linter errors (@MyroslavVozniak, #3246)
- Disabled cash app from stripe checkout (@MyroslavVozniak, #3243)

### 2026-01-20
- Added project subscription webhook support (@MyroslavVozniak, #3237)
- Comm style (@s-wang-la, #3242)
- Add pagination and filtering to /v1/admin/accounts endpoint (@xiangkangjw, #3241)
- Bump pal agents and tools to update vapi tool (@crooksjeff, #3240)
- Bump pal-agents and add comida to use new flow (@crooksjeff, #3239)
- Added chat filler words to pal-agents streaming flow (@crooksjeff, #3238)
- Vapi transfer from raw config (@ronald-palona, #3236)
- Fix credential name mismatch in Toast tool (@TomYang-TZ, #3235)
- Vapi transfer from raw config (@ronald-palona, #3234)
- Routine performance improvement (@BruceJinProactive, #3233)
- Temporarily use raw_config to load Vapi Tool instead of DB (@ronald-palona, #3232)
- Add TTL cache for feature flag checks (@ronald-palona, #3229)
- Fix: Routine Execution N+1 (@BruceJinProactive, #3231)
- Fixed project checkout callback duplicate key (@MyroslavVozniak, #3230)
- Added project level to checkout callback (@MyroslavVozniak, #3227)
- Fix: propagate DB pool timeout errors to prevent connection exhaustion (@xiangkangjw, #3228)
- Fixed project sub creation process (@MyroslavVozniak, #3226)
- Added checkout session for projects (@MyroslavVozniak, #3225)

### 2026-01-19
- Fix: skip callerId for SIP transfers to preserve sipVerb: dial (@andrewhcli, #3224)
- Fix: build schedule response before commit to avoid greenlet error (@teresatian-cell, #3223)
- Fix: add session refresh after schedule update to prevent async context error (@teresatian-cell, #3222)
- Remove excess parameters from toast tool (@graydonpower-dev, #3220)
- Remove sandbox argument from toast tool (@TomYang-TZ, #3221)
- Add reset submission logic (@BruceJinProactive, #3219)
- Added project level plan switch (@MyroslavVozniak, #3218)
- Fix: add cascade delete to account relationships (@teresatian-cell, #3209)
- Multi transfer app changes (@ronald-palona, #3217)
- Add migration to copy transfer_phone_number to contacts table (@ronald-palona, #3216)

### 2026-01-17
- Update ordering prompt (@s-wang-la, #3214)

### 2026-01-16
- Update general and ordering prompt (@s-wang-la, #3213)
- Adjust menu info prompt (@s-wang-la, #3212)
- Bump pal-agents - use azure now (@crooksjeff, #3211)
- Add half-and-half instructions to system prompt yaml file for AdoraV2 (@Tim-Yang-YTY, #3208)
- Feat: add configurable caller ID display for call transfers (@andrewhcli, #3202)

### 2026-01-15
- Docs: update CLAUDE.md files (@xiangkangjw, #3167)
- AdoraV2: Redesign Menu Formatter (@Tim-Yang-YTY, #3207)
- Update v2 general prompt (@s-wang-la, #3200)
- Adding slack bot for feedback (@kellyguan-create, #3206)
- Fix: structure output description (@BruceJinProactive, #3204)
- AdoraV2: Include allow halving info in size listing (@Tim-Yang-YTY, #3203)
- Fixed resend invitation expiration (@MyroslavVozniak, #3201)

### 2026-01-14
- Fix Toast stock removal with trailing punctuation normalization. Add debug logs (@TomYang-TZ, #3197)
- Feat: integrate reservation/waitlist metrics into analytics and Slack (@andrewhcli, #3095)
- Fix gemini issue (@BruceJinProactive, #3196)
- Fix: Adding the secret (@BruceJinProactive, #3195)
- AdoraV2: Include half-and-half ordering details in item comments; added complete order object to trace (@Tim-Yang-YTY, #3194)
- Add purpose-based call transfer routing (@ronald-palona, #3159)
- Added new feedback tags (@kellyguan-create, #3193)
- Feat: create by choosing model (@BruceJinProactive, #3191)
- AdoraV2: Change wording to indicate half and half not allowed (@Tim-Yang-YTY, #3192)
- Updated API for feedback added author_name (@kellyguan-create, #3189)
- AdoraV2: always explicitly show whether items and modifier groups are eligible for half-and-half ordering (@Tim-Yang-YTY, #3187)
- Feat: Add more models to monitoring (@BruceJinProactive, #3185)
- Register StoreMessagingTool in tool registry (@s-wang-la, #3188)
- Fixed invoice display name (@MyroslavVozniak, #3186)
- Added author_name to Feedback table (@kellyguan-create, #3183)
- Added endpoints for sending analytics invoice emails (@MyroslavVozniak, #3184)
- AdoraV2: Add allow_halving info to menu and KB (@Tim-Yang-YTY, #3176)
- AdoraV2: Add phone number formatter (@Tim-Yang-YTY, #3182)
- Add implementation of texting store (@s-wang-la, #3180)
- Update toast's default ordering prompts (@TomYang-TZ, #3181)
- Semi-intelligent filler word selection (@ronald-palona, #3175)
- Fixed remove pending invite (@MyroslavVozniak, #3179)

### 2026-01-13
- Add display_name to me/accounts endpoint response (@xiangkangjw, #3178)
- Add messaging tool skeleton (@s-wang-la, #3177)
- Revert: remove callerId from VAPI transfer payload (@andrewhcli, #3174)
- AdoraV2: Update Order Prompt to Support Half and Half Order (@Tim-Yang-YTY, #3168)
- Add debug logging (@s-wang-la, #3171)
- Fixed project stripe customer naming convension (@MyroslavVozniak, #3170)
- Changed project Stripe customer naming convention (@MyroslavVozniak, #3169)
- AdoraV2: Enable half and half order (@Tim-Yang-YTY, #3158)
- Migrate to Azure Openai (@BruceJinProactive, #3166)

### 2026-01-12
- Added trialing to get active subscription (@MyroslavVozniak, #3165)
- Fixed invitation recreate password when expired (@MyroslavVozniak, #3164)
- Add POST /monitoring/capture endpoint to record capture timestamps (@xiangkangjw, #3163)
- Fix project stripe customer creation (@MyroslavVozniak, #3160)
- Added invitation_id to TeamInvitationResponse schema (@MyroslavVozniak, #3161)
- AdoraV2: Update Coupon docstring (@Tim-Yang-YTY, #3156)
- Debug: Find the root cause for add response (@BruceJinProactive, #3155)
- Fix: greenlet issue and mistrace in monitoring llm (@BruceJinProactive, #3154)
- Add API endpoint to list knowledge base namespaces with filtering (@devin-ai, #3150)
- Complete small todo in codebase (@xiangkangjw, #2844)
- Fix: Greenlet issue on submission API (@BruceJinProactive, #3153)
- Revert "Revert "feat: add channel-based conversation scoping"" (@xiangkangjw, #3151)
- Use feature as gatekeeper (@s-wang-la, #3149)
- Fix: Greenlet issue on submission API (@BruceJinProactive, #3152)
- Fix: char limitation (@BruceJinProactive, #3140)
- Convert vapi_tool to async (@ronald-palona, #3137)

### 2026-01-11
- Add endpoint (@s-wang-la, #3148)
- Add feature service (@s-wang-la, #3147)
- Add feature repository (@s-wang-la, #3146)
- Add table to control feature enabledment (@s-wang-la, #3145)

### 2026-01-10
- Fix: set callerId on VAPI transfers to show AI agent's phone number (@andrewhcli, #3144)

### 2026-01-09
- Feat: add channel-based conversation scoping (@xiangkangjw, #3141)
- Feat: add reservation/waitlist tracking DB schema (@andrewhcli, #3093)
- Add CI check to enforce DB schema changes in separate PRs (@xiangkangjw, #3139)
- Fix: post routine greenlet (@BruceJinProactive, #3138)
- Fixed remove subscription item bug (@MyroslavVozniak, #3136)
- Feat: Fixing the reference images upload logic (@BruceJinProactive, #3135)

### 2026-01-08
- Add get all coupons endpoint (@MyroslavVozniak, #3134)
- AdoraV2: Update order processing failure detection logic (@Tim-Yang-YTY, #3133)
- Update default channel (@s-wang-la, #3130)
- AdoraV2: Update extraction prompt to clarify JSON structure requirements (@Tim-Yang-YTY, #3131)
- Add length-based filler word selection (@ronald-palona, #3123)
- Toast new partner webhook (@s-wang-la, #3126)
- AdoraV2: Implement coupon code validation in order processing (@Tim-Yang-YTY, #3129)
- Fix: routine service (@BruceJinProactive, #3128)
- AdoraV2: Rewrite order extraction; move promise_date_time to function param (@Tim-Yang-YTY, #3127)
- Add coupons APIs and logic (@MyroslavVozniak, #3119)

### 2026-01-07
- Upgrade pyright to 1.1.407 and fix validation script (@xiangkangjw, #3125)
- Fix: Change Camera not found for upload to warning (@BruceJinProactive, #3124)
- Add phone number existence check (@s-wang-la, #3122)
- Finetuning mnitoring service (@BruceJinProactive, #3121)
- Toast: adjust get existing order logic (@TomYang-TZ, #3014)
- Added coupon_id field to account and projects tables (@MyroslavVozniak, #3118)
- AdoraV2: Adjust Order JSON structure rules (@Tim-Yang-YTY, #3117)

### 2026-01-06
- AdoraV2: Update item_id and size_id fields to be mandatory; add more traces for fulfill order (@Tim-Yang-YTY, #3116)
- Add Stripe functionality on project level (@MyroslavVozniak, #3103)
- Greenlet error (@crooksjeff, #3112)
- Add ingestion (@crooksjeff, #3111)
- Add channel to message and conversation (@xiangkangjw, #3019)
- Fix: add mode to transferPlan for SIP transfers via control URL (@andrewhcli, #3106)
- Organized llm code (@BruceJinProactive, #3110)
- AdoraV2: Fix Token Fetching Endpoint for QA Stores (@Tim-Yang-YTY, #3109)
- Bump pal agents to add memmory background task for first message/cach (@crooksjeff, #3107)
- Update CODEOWNERS to allow coderabbitai approve dep version bumps (@renkelvin, #3102)
- Format iamge url in response (@BruceJinProactive, #3104)
- Fixed Stripe webhook secret retrieval (@MyroslavVozniak, #3105)
- Bump pal agents for memory cache (@crooksjeff, #3101)

### 2026-01-05
- Rearrange cap apis to admin (@s-wang-la, #3090)
- Bump pal agents for knowledge cache (@crooksjeff, #3100)
- Fix: Turnning run details to be image-url (@BruceJinProactive, #3099)
- Removed unnecessary logging on call length tracking (@MyroslavVozniak, #3098)
- Feat: delete monitoring run api (@BruceJinProactive, #3097)
- Added vapi call length check (@MyroslavVozniak, #3096)
- Bump pal agents (@crooksjeff, #3092)
- AdoraV2: Added QA store secret fetching logic (@Tim-Yang-YTY, #3091)
- Feat: save runs result to DB (@BruceJinProactive, #3087)
- Fix: change all the timezone to PST (@BruceJinProactive, #3086)
- Feat: implement LLM analysis for monitoring runs with image processing (@BruceJinProactive, #3083)
- Fixed project subscription mapper initializing (@MyroslavVozniak, #3084)
- Fix: use webhook approach for SIP transfers to support PSTN callers (@andrewhcli, #3082)
- Added fields from account subscription to project (@MyroslavVozniak, #3079)
- Fix duplicate change log on revert (@devin-ai, #3080)
- Add revert change log endpoint (@devin-ai, #3063)
- Add apis to manage capabilities (@s-wang-la, #3078)
- Fix: tighten conversion table column headers (@andrewhcli, #3077)

### 2026-01-04
- Fix: remove unused signal source lookup endpoint and related code (@BruceJinProactive, #3076)
- Feat: add endpoint to retrieve signal source ID by camera ID (@BruceJinProactive, #3075)
- Fix: increase engagement table column spacing to 2 chars (@andrewhcli, #3074)
- Fix: shorten Transfer Rate to Xfer % in engagement table (@andrewhcli, #3073)
- Add prompt merge (@s-wang-la, #3072)
- Load default v2 prompt (@s-wang-la, #3071)
- Add repository (@s-wang-la, #3070)
- Fix: tighten engagement table column spacing to prevent wrapping (@andrewhcli, #3069)

### 2026-01-03
- Add agent_capability and actions table (@s-wang-la, #3066)
- Fix: use VAPI transferCall tool for SIP transfers (@andrewhcli, #3068)
- Refactor: rename analytics report metrics for clarity (@andrewhcli, #3067)

### 2026-01-02
- Add md for new prompt management (@s-wang-la, #3065)
- AdoraV2: Update fulfill_order docstring and add trace span (@Tim-Yang-YTY, #3064)
- AdoraV2: Fix input parameters to be compliant with OpenAI strict mode (@Tim-Yang-YTY, #3062)

## 2025-12

### 2025-12-31
- Fix: routine service async I/O improvements (@xiangkangjw, #3060)
- Fix: use sipVerb dial for SIP transfers to support PSTN callers (@andrewhcli, #3059)
- Feat: enhance update_monitoring_config to support image management op (@BruceJinProactive, #3058)
- Fix: resolve greenlet_spawn error when creating routines (@xiangkangjw, #3055)
- Feat: add endpoint to lookup signal source ID by camera ID (@BruceJinProactive, #3054)
- Fix: enhance delete_config to clean up S3 storage after deletion (@BruceJinProactive, #3053)
- Fix: transform reference image URLs to presigned S3 URLs in config re (@BruceJinProactive, #3052)
- Feat: enhance logging in create_monitoring_config for better traceabi (@BruceJinProactive, #3051)

### 2025-12-30
- Fix: resolve S3 upload issue by storing config_id and refreshing sess (@BruceJinProactive, #3049)
- Fix: mark JSONB field as modified in create_monitoring_config (@BruceJinProactive, #3048)
- Fix create config (@BruceJinProactive, #3047)
- Feat: auto-generate executions on routine creation (@xiangkangjw, #3046)
- Remove unit testing scripts and GitHub Actions (@renkelvin, #3037)
- Removed duration tracking for now (@MyroslavVozniak, #3043)
- Fixed call length tracking mechanism (@MyroslavVozniak, #3042)
- Implement Routines system for restaurant operations management (@xiangkangjw, #3039)
- Added call duration length logging (@MyroslavVozniak, #3041)
- Added usage reporting filtering logic (@MyroslavVozniak, #3040)
- Added stripe customer id to projects (@MyroslavVozniak, #3038)

### 2025-12-29
- Add routines database tables for checklist feature (@xiangkangjw, #3030)
- AdoraV2: Redesign Input Handling (@Tim-Yang-YTY, #3033)
- Explicitly disbale LLMObs for testing requests (@akshaybhatia-ops, #3032)
- Remove logging if the chat request is testing (@akshaybhatia-ops, #3009)
- Implement internal API endpoints for monitoring image processing and (@BruceJinProactive, #3029)
- Billing docs in claude (@xiangkangjw, #3028)
- Monitoring apis (@BruceJinProactive, #3027)

### 2025-12-26
- Fix conversation lookup to filter by project_id (@xiangkangjw, #3026)
- Add day of week to special hours format (@xiangkangjw, #3025)
- Reduce business hours update frequency to 8 hours (@xiangkangjw, #3024)
- Include special hours in store_hours field (@xiangkangjw, #3023)
- Refactor Stripe webhook handlers and fix architecture violations (@xiangkangjw, #3021)

### 2025-12-24
- Add Stripe subscription statuses (@xiangkangjw, #3020)

### 2025-12-23
- Fix greenlet_spawn error when persisting payment link SMS (@xiangkangjw, #3018)
- Adding more filler (@s-wang-la, #3017)
- Fix Firecrawl and OpenAI to use server secrets instead of client secrets (@xiangkangjw, #3013)
- Use vapi tool (@crooksjeff, #3016)
- Fix greenlet_spawn error when creating/updating signal sources (@xiangkangjw, #3015)
- Add monitoring schemas (@BruceJinProactive, #3012)
- Add mandatory camera_id to signal source config for S3 path validation (@xiangkangjw, #3011)
- (DB): Add monitoring_configs and monitoring_runs tables (@BruceJinProactive, #3010)
- Add recurring credit grants table (@MyroslavVozniak, #3008)
- Upgrade pal-agents (@crooksjeff, #3007)
- Add Signal Sources V1 API (cameras) with project-level routes (@xiangkangjw, #3005)

### 2025-12-22
- Added pal-agents update + obs (@crooksjeff, #3006)
- (fix) include adora paid status (@BruceJinProactive, #3004)
- Add signal_sources and signal_feeds database tables (@xiangkangjw, #3003)
- (doc) add docs for monitoring service (@BruceJinProactive, #2999)
- Storing IDs before commit and or {} pattern (@crooksjeff, #3002)
- Feat: update order status to paid after checkout completion (@devin-ai, #2998)
- Add version-aware database migrations with automatic rollback (@xiangkangjw, #2909)
- Should fix greenlet (@crooksjeff, #3001)
- Add Signal Sources TDD for V1 (cameras only) (@xiangkangjw, #3000)
- Move imports to see if it fixes greenlet error for vapi (@crooksjeff, #2997)
- Add streaming to pal-agents flow (@crooksjeff, #2996)
- Implement Toast `_save_order_to_db` (@TomYang-TZ, #2994)
- AdoraV2: Adding additionalProperties: false in the JSON schema for Op (@Tim-Yang-YTY, #2995)
- Added output fields and message history for sms texting (@crooksjeff, #2993)
- AdoraV2: Include Order Items in Context (@Tim-Yang-YTY, #2992)
- Decouple to slack service (@BruceJinProactive, #2990)

### 2025-12-21
- AdoraV2: Refactor get_relevant_doc (@Tim-Yang-YTY, #2986)
- AdoraV2: Fix the tuple indexing error in address validation handling (@Tim-Yang-YTY, #2988)
- AdoraV2: Fix validate_address return type checking (@Tim-Yang-YTY, #2987)
- AdoraV2: Fix check_address output length check (@Tim-Yang-YTY, #2985)
- AdoraV2: Refactoring order ingestion logic (@Tim-Yang-YTY, #2984)
- Handle unconfigured restaurant webhooks gracefully (@xiangkangjw, #2982)

### 2025-12-20
- Remove prompt that closes conversation after payment link (@xiangkangjw, #2981)
- Filter VapiTool to only be available for voice channel (@xiangkangjw, #2980)
- Add debugging improvements and channel tracking for messages (@xiangkangjw, #2979)
- Persist outbound SMS messages to message table (@xiangkangjw, #2977)
- Handle 'Call Not Active' error gracefully in VapiTool (@xiangkangjw, #2978)
- Temp hacky code to test prompt (@s-wang-la, #2976)

### 2025-12-19
- Update status to Order table (@s-wang-la, #2975)
- AdoraV2: Fix address response parsing (@Tim-Yang-YTY, #2973)
- AdoraV2: Refactor Check Address flow (@Tim-Yang-YTY, #2972)
- Reverted pal-mono agent to use azure openai (@ahadjiva-p, #2960)
- AdoraV2: Redesign delivery checkout flow (@Tim-Yang-YTY, #2971)
- AdoraV2: Update address input handling (@Tim-Yang-YTY, #2970)
- AdoraV2: Updated DeliveryAddress class to forbid extra fields. (@Tim-Yang-YTY, #2969)
- Update construct order system prompt (@TomYang-TZ, #2967)
- Revert: Add ECS deployment verification to release workflow (#2958) (@xiangkangjw, #2965)

### 2025-12-18
- Cleanup redundant logic (@s-wang-la, #2966)
- Add ECS deployment verification to release workflow (@xiangkangjw, #2958)
- Add resolution handlers for histories and feedbacks resource types (@xiangkangjw, #2959)
- Add logging to update_menu endpoint for debugging 503 errors (@xiangkangjw, #2964)
- Store numbers in order table (@s-wang-la, #2963)
- Add store number to toolMetadata (@s-wang-la, #2962)
- Add phone numbers to order table (@s-wang-la, #2961)
- Change adora menu updater to pull from adora_tool args (@graydonpower-dev, #2957)
- AdoraV2: Simplify input handling in check address (@Tim-Yang-YTY, #2956)
- Remove the 10 sec rule for usage tracking (@MyroslavVozniak, #2955)
- AdoraV2: Update promiseDateTime description (@Tim-Yang-YTY, #2954)
- Removed the 10 sec rule for usage tracking for now (@MyroslavVozniak, #2953)
- AdoraV2: Use OpenAI for construction order (@Tim-Yang-YTY, #2952)
- Added extensive logging to identify call length (@MyroslavVozniak, #2951)
- Adorav2 llama orderconstruction (@Tim-Yang-YTY, #2950)
- Fixed call tracking vapi (@MyroslavVozniak, #2949)
- AdoraV2: Update classes.py and _implementation.py (@Tim-Yang-YTY, #2948)
- AdoraV2: Fix order construction (@Tim-Yang-YTY, #2947)
- Fix 403 authorization errors being logged at error level (@xiangkangjw, #2946)
- AdoraV2: Refine Order Construction Logic (@Tim-Yang-YTY, #2945)
- Refactor hosted resy tool to use new api endpoint (@graydonpower-dev, #2943)
- (feat): Add Palona Slack Channel (@BruceJinProactive, #2944)

### 2025-12-17
- AdoraV2: Add Populated by name to Delivery Class; update type id after address validation (@Tim-Yang-YTY, #2942)
- AdoraV2: Adding logs for fullfill Order (@Tim-Yang-YTY, #2941)
- Reorder Store prompt and Agent prompt (@s-wang-la, #2938)
- Clean up unused knowledge provider (@s-wang-la, #2937)
- Fix resource_id validation for histories and feedbacks (@xiangkangjw, #2936)
- AdoraV2: Update DeliveryAddress lat/lng assignment when valid (@Tim-Yang-YTY, #2935)
- Add pal-agents v0.2.0 (@crooksjeff, #2929)
- Fix adorav2 address payload typo (@Tim-Yang-YTY, #2933)
- Fix SQLAlchemy MissingGreenlet errors in VAPI implementation (@xiangkangjw, #2931)
- AdoraV2: Address Validation Debugging (@Tim-Yang-YTY, #2932)
- Fix lat/lon addition to Delivery Object (@Tim-Yang-YTY, #2928)
- AdoraV2: Process Order for Delivery (@Tim-Yang-YTY, #2927)

### 2025-12-16
- AdoraV2: Fix Process Order Input Class Alias (@Tim-Yang-YTY, #2926)
- AdoraV2: Add logging for processOrder API call (@Tim-Yang-YTY, #2925)
- AdoraV2: Process Order API Integration (@Tim-Yang-YTY, #2922)
- Changed truefoundry client into a singleton, increased timeout timer (@ahadjiva-p, #2923)
- Proposal: Restaurant Operations System (@xiangkangjw, #2838)
- AdoraV2: Fix val order response parsing issue (@Tim-Yang-YTY, #2921)
- AdoraV2: set default email (@Tim-Yang-YTY, #2919)
- Update safemode for prod adora menu updater testing (@graydonpower-dev, #2917)
- AdoraV2: Fix on get_store_id and declare v2 api functions (@Tim-Yang-YTY, #2918)
- AdoraV2: Fixed query engine namespace from "agent" to "agents" (@Tim-Yang-YTY, #2916)
- Remove thread_ts parameter from send_report_to_slack function and rel (@BruceJinProactive, #2915)
- AdoraV2: Validate Order Implementation (@Tim-Yang-YTY, #2910)
- Update Square to Use AWS Secrets Manager (@Tim-Yang-YTY, #2830)
- Revert "Moved usage tracking to conversation level" (@MyroslavVozniak, #2913)
- Added accept all invitations (@MyroslavVozniak, #2908)

### 2025-12-15
- AdoraV2: Simplify Check Address return handling (@Tim-Yang-YTY, #2911)
- Moved usage tracking to conversation level (@MyroslavVozniak, #2907)
- AdoraV2: quick fix on passing store_id key (@Tim-Yang-YTY, #2906)
- AdoraV2: Implement Check Address API (@Tim-Yang-YTY, #2894)
- Added get server secret to invitation token decode (@MyroslavVozniak, #2905)
- Implement Async LLM Calls used in Tool Calling (@Tim-Yang-YTY, #2899)
- Implement Async Secret Fetching (@Tim-Yang-YTY, #2898)
- Moved get invitation jwt secret to a method (@MyroslavVozniak, #2904)
- Invitation jwt password embedding (@MyroslavVozniak, #2888)
- Fix webhook naming issue (@s-wang-la, #2902)
- Add async sleep to instagram functions (@graydonpower-dev, #2903)
- Improve Toast checkout error handling and validation (@TomYang-TZ, #2901)
- Rename dataset endpoint from /datasets to /generate-dataset (@akshaybhatia-ops, #2900)
- Introduced stripe invoicing (@MyroslavVozniak, #2883)
- Added to only report meaningful calls usage (@MyroslavVozniak, #2897)

### 2025-12-13
- Refactore adora v2 api level (@s-wang-la, #2896)
- Move token fetch to util (@s-wang-la, #2895)
- AdoraV2: Integrate Get Store Info API (@Tim-Yang-YTY, #2893)
- AdoraV2: V2 Token Endpoint Fix (@Tim-Yang-YTY, #2892)
- AdoraV2: Implement store status checking tool (@Tim-Yang-YTY, #2886)

### 2025-12-12
- Add invitation validation for existing members and pending invitations (@xiangkangjw, #2889)
- Fix: use email in permission denied logs, add user_id to extra (@xiangkangjw, #2891)
- Add async waits for adora menu updater (@graydonpower-dev, #2890)
- Unify Toast checkout tool to single name to fix agent recognition with hosted checkout (@TomYang-TZ, #2887)
- Convert state names to ISO 3166-2 abbreviations for Toast API (@TomYang-TZ, #2884)
- Made usage tracking log info (@MyroslavVozniak, #2885)

### 2025-12-11
- Docs: clarify transfer field naming in db/CLAUDE.md (@xiangkangjw, #2864)
- Fix: add warning log when voice message missing call_id (@xiangkangjw, #2881)
- Turn off menu updater safe mode (@graydonpower-dev, #2880)
- Add tool_metadata parameter to AdoraV2Tool (@Tim-Yang-YTY, #2879)
- Adora menu updater adjust wait times (@graydonpower-dev, #2878)
- Fix: propagate call_id through voice streaming flow for VAPI call transfers (@xiangkangjw, #2876)
- Adjust adora namespace population retry (@graydonpower-dev, #2877)
- AdoraV2 tool skeleton implementation (@Tim-Yang-YTY, #2865)
- Adora retry populating namespace (@graydonpower-dev, #2875)
- Add call data and monitor data log in handle_assistant_request (@TomYang-TZ, #2873)
- Adora menu updater namespace deletion retry (@graydonpower-dev, #2872)
- Add missing db refresh (@xiangkangjw, #2871)
- Revert: fix: improve VAPI error handling and prevent greenlet_spawn errors (#2868) (@xiangkangjw, #2870)
- Add adora menu updater delay (@graydonpower-dev, #2869)
- Fix: improve VAPI error handling and prevent greenlet_spawn errors (@xiangkangjw, #2868)
- Adora menu updater checks for empty name space (@graydonpower-dev, #2867)
- Add error log in Vapi handle assistant request (@TomYang-TZ, #2866)
- Fix: adjust logging levels for better operational visibility (@xiangkangjw, #2863)

### 2025-12-10
- Feat: improve VAPI logging for call transfer debugging (@xiangkangjw, #2862)
- Fix: separate voice message creation for reliable call transfer (@xiangkangjw, #2859)
- Added endpoint to assign account to a user (@MyroslavVozniak, #2858)
- Update menu updater project id (@graydonpower-dev, #2856)
- Add safemode for adora menu updater testing (@graydonpower-dev, #2855)
- Adora webhook paid status update (@s-wang-la, #2854)
- Docs: add CLAUDE.md for database layer (@xiangkangjw, #2824)
- Feat: add storeName to hosted checkout payload and fix subtotal calculation (@devin-ai, #2853)
- Updated local.env.example to reflect truefoundry implementation (@ahadjiva-p, #2829)
- -Add api to submit dataset-generation request to event brid (@akshaybhatia-ops, #2850)
- Made the endpoint admin-only (@MyroslavVozniak, #2852)
- Toast tool: set orderingagent@palona.ai as the default email address (@TomYang-TZ, #2851)
- Added get user accounts by email logic (@MyroslavVozniak, #2849)
- Fix webhook event attributes (@s-wang-la, #2848)

### 2025-12-09
- Show customer name in tab name (@TomYang-TZ, #2845)
- Update api/routes/CLAUDE.md for RBAC-based authorization (@xiangkangjw, #2842)
- Revert " -Add api to submit dataset-generation request to ev (@akshaybhatia-ops, #2847)
- -Add api to submit dataset-generation request to event bridge (@akshaybhatia-ops, #2812)
- Change resy api key cache ttl (@graydonpower-dev, #2846)
- Remove account_names from UserContext and clean up dead code (@xiangkangjw, #2843)
- Adora menu updater endpoint (@graydonpower-dev, #2832)
- Fix display project (@BruceJinProactive, #2841)

### 2025-12-08
- Remove custom:account_name and custom:account_names Cognito attributes (@xiangkangjw, #2839)
- Enhance Slackbot integration logging and refine conversion table disp (@BruceJinProactive, #2837)
- Keep polishing analytics (@BruceJinProactive, #2836)
- Skip store availability check when skip_order_submission is enabled (@TomYang-TZ, #2835)
- Refactor conversion and engagement table functions for generic handli (@BruceJinProactive, #2834)
- Fixed stripe signature header (@MyroslavVozniak, #2831)
- Registered Stripe webhook directly to avoid 403 issue (@MyroslavVozniak, #2828)
- Added stripe integration with webhook (@MyroslavVozniak, #2826)
- Fixed async notification sending (@MyroslavVozniak, #2827)

### 2025-12-07
- Add skip_order_submission flag for Toast checkout testing (@TomYang-TZ, #2825)

### 2025-12-05
- Inject uploaded knowledge text (@crooksjeff, #2822)
- Feat: Slack - direct message (@BruceJinProactive, #2821)
- Fix-Endpoint (@aagamshah-proactive, #2820)
- Refactor: use async publish_event and add internal catering events endpoint (@devin-ai, #2810)
- Not use OpenAI to construct orders in the Square (@Tim-Yang-YTY, #2819)
- Added notification preferences endpoints (@MyroslavVozniak, #2818)
- Added billing types and subs service integration points (@MyroslavVozniak, #2817)

### 2025-12-04
- Added notification preferences to accounts table (@MyroslavVozniak, #2816)
- Feat: add rerun functionality for checkpoint runs and improve image d (@BruceJinProactive, #2815)
- Update CODEOWNERS (@renkelvin, #2814)
- Feat: implement batch deletion of checkpoint runs by their IDs (@BruceJinProactive, #2813)
- Remove RBAC launch flag - feature is now fully launched (@xiangkangjw, #2808)
- Add-Post-Endpoint (@aagamshah-proactive, #2811)
- Fix: use EVENT_BUS_NAME env var instead of hardcoded bus name in catering service (@devin-ai, #2809)

### 2025-12-03
- Pal agent (@crooksjeff, #2795)
- Square tool: use OpenAI to construct Order (@Tim-Yang-YTY, #2806)
- Add missing function signature (@TomYang-TZ, #2805)
- Fix admin role determination to use pool source and cognito groups (@xiangkangjw, #2804)
- Toast tool validate dining options and expose _`get_relevant_docs` errors (@TomYang-TZ, #2803)
- Add structured prompt menu format output for Toast menu processor (@TomYang-TZ, #2802)

### 2025-12-02
- Add admin override to all RBAC permission checkers (@xiangkangjw, #2801)
- Migrate all REST APIs to RBAC permission system (@xiangkangjw, #2800)
- Allow admins to bypass RBAC permission checks (@xiangkangjw, #2799)
- Enable RBAC by default (@xiangkangjw, #2798)
- Added business hours to get project (@MyroslavVozniak, #2797)
- Revert "Add Pal-Agents" (@crooksjeff, #2796)
- Implement RBAC Phase 2 migration with feature flag support (@xiangkangjw, #2794)
- Truefoundry setup (@ahadjiva-p, #2767)
- Add target menu for toast menu parser (@s-wang-la, #2793)
