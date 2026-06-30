# Mercury Engagement Summary Metrics

Date: 2026-06-28
Task: PAL-11840

## Summary

Slack Mercury daily/account engagement reports now replace the derived
`RES w/o Xfer%` column with three post-call quality metrics:

- `Negative Sentiment`: negative user satisfaction calls divided by all calls.
- `Transfer w Agent Fault`: transfer-agent-fault calls divided by transferred calls.
- `Spam %`: non-legitimate restaurant calls divided by all calls.

## Implementation Notes

- The change reuses existing analytics report outputs; it does not add a new DB
  query or LLM classifier.
- Negative satisfaction comes from `Call Time Metrics` negative-call counts.
- Transfer-agent-fault counts come from `Transfer Reason Distribution`; the
  denominator is the existing transferred-call count from `Call Time Metrics`.
- Spam counts come from `Call Quality Distribution` rows where
  `is_legitimate` is false; the denominator is all calls in the report scope.
- Slack renders the new percentage metrics with raw numerator/denominator
  counts, e.g. `13.3% (2/15)`, so reviewers can see the backing sample size.
- Zero-denominator percentages render as `N/A`.
