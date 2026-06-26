# Vision Confidence Contract Removal

## Summary

Removed Vision model confidence from the backend API and service contracts.
Entity observations, current-state responses, state-change event creation, and
state-change event responses now expose the observed state and supporting
reasoning without a confidence score.

## Behavior

- Vision prompts no longer ask the model to emit `confidence`.
- The entity-state response parser only consumes `reason` and `state`.
- Smoothing decisions are based on state voting only.
- State-change events no longer accept or return confidence.
- Historical current-state metadata that still contains confidence is ignored
  on read so existing rows remain compatible.

## Notes

The database column removal is tracked in the upstream schema-only PR. This
runtime change removes active producers and consumers of Vision confidence.
