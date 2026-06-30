# Vision Structured Observations Runtime

## Summary

The Vision camera configuration API now carries
`structured_observations_enabled` through create, update, repository, and
response paths. When the flag is enabled for a camera configuration, the Vision
observation runtime asks the model to return a prompt-defined `observations`
object before `reason` and `state` for each monitored entity.

Existing camera configurations keep the default `false` behavior and continue
to use the strict state-only output contract.

## Runtime Behavior

Structured observations are intentionally use-case-specific. The backend does
not define a universal schema for the `observations` object; each camera prompt
owns the keys and shape. For example, a cake-display prompt can request lane
counts, while another prompt can use a different observation structure.

When structured observations are enabled, the runtime uses JSON object mode
instead of strict JSON schema output so providers can preserve prompt-defined
fields inside the open `observations` object. When the flag is disabled, the
runtime keeps the existing strict schema with `reason` and `state`.

## Compatibility

The final business behavior remains state-driven. Smoothing, violation
transitions, and customer-facing Vision events continue to use the selected
`state`; `observations` is returned for debugging, auditing, and prompt-level
inspection.
