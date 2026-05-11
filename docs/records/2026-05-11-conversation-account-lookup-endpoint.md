# Conversation Account Lookup Endpoint

**Date**: 2026-05-11
**Status**: Implemented

## Context

Admin console conversation deep-links (e.g., from Slack notifications) use the format:
`/hosting/conversations?conversationId=<uuid>`

These links don't carry account context. When a user with access to multiple accounts opens such a link while viewing a different account, the conversation cannot be found in the current account's conversation list.

## What Shipped

### API Endpoint


| Method | Path                                                | Status | Description                                      |
| ------ | --------------------------------------------------- | ------ | ------------------------------------------------ |
| GET    | `/v1/admin/conversations/{conversation_id}/account` | 200    | Returns the account_name owning the conversation |


Requires `authenticate_user`. Verifies the caller has `account.read` permission on the conversation's account before returning. Returns 404 if the conversation doesn't exist or the user lacks access (no information leakage).

### Response Schema

`ConversationAccountLookupResponse` in `api/schemas/admin/conversation.py`:

```python
class ConversationAccountLookupResponse(BaseModel):
    account_name: str = Field(..., description="The account name that owns this conversation")
```

### Frontend Changes (pal-admin-console)

- `**actions.ts**`: Added `lookupConversationAccount(conversationId)` server action
- `**ConversationsList.tsx**`: Updated URL-restoration `useEffect` — when a conversation isn't found after expanding time filter to "all", calls the lookup endpoint and switches to the correct account via `switchAccountByName()`

### Flow

1. User pastes link → page loads with current (wrong) account
2. Conversation not found in paginated list → time filter expanded to "all"
3. Still not found after data loads → `lookupConversationAccount()` called
4. Backend returns correct account_name → `switchAccountByName()` triggers page reload
5. Page reloads with correct account → conversation found and selected

## Files Changed

- `api/schemas/admin/conversation.py` — added `ConversationAccountLookupResponse`
- `api/routes/admin/_conversation.py` — added `lookup_conversation_account()`
- `api/routes/admin/__init__.py` — added route registration
- `tests/api/routes/admin/test_conversation.py` — added `TestLookupConversationAccount`
- `pal-admin-console/components/(console)/conversations/actions.ts` — added server action
- `pal-admin-console/components/(console)/conversations/components/ConversationsList.tsx` — account switch logic

