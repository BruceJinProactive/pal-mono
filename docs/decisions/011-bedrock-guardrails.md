# ADR-011: Bedrock Guardrails for Content Safety

> **Status:** Deprecated
> **Date:** 2024-01-01
> **Decision makers:** Shuo, Jeff Crooks

## Context

The platform needs robust content safety checks to filter harmful user inputs and agent outputs. The system is already hosted on AWS, making AWS-native solutions a natural fit.

## Decision

The platform uses AWS Bedrock Guardrails for content safety. The `check_input_bedrock` function implements input filtering before agent processing.

## Alternatives Considered

- **Custom content moderation** — Significant ML/engineering effort to build and maintain
- **OpenAI Moderation API** — Provider-specific; doesn't cover all content safety needs
- **Guardrails AI (open source)** — Additional dependency; Bedrock integrates natively with existing AWS infrastructure

## Consequences

- **Easier:** Integrated with existing AWS infrastructure; managed service with AWS support
- **Harder:** AWS lock-in for the safety layer; dependent on AWS service availability
