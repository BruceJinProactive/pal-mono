"""Tests for services/eval_service/_http_voice_driver.py.

The driver's contract is narrow: POST /v1/internal/voice/init on first
turn, stream /v1/chat/completions per turn, POST /v1/internal/voice/end-call
on aclose(). The tests build a throwaway FastAPI app that handles those
three routes and assert the driver's behaviour against it.

No mocks of ``httpx`` or ``ASGITransport`` — they are the exact
production transport. The seams are the three endpoint handlers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from services.eval_service._http_voice_driver import HttpVoiceDriver

# ---------------------------------------------------------------------------
# Test harness: a minimal FastAPI app that records what the driver sent
# ---------------------------------------------------------------------------


class _StubApp:
    """Bundle a FastAPI app with the recorded requests its handlers saw."""

    def __init__(
        self,
        *,
        init_status: int = 200,
        end_status: int = 200,
        end_conversation_id: str | None = None,
        turn_replies: list[str] | None = None,
        chat_status: int = 200,
        chat_emits_done_sentinel: bool = True,
    ) -> None:
        self.app = FastAPI()
        self.init_calls: list[dict[str, Any]] = []
        self.end_calls: list[dict[str, Any]] = []
        self.chat_calls: list[dict[str, Any]] = []
        self._turn_replies = list(turn_replies or ["default reply"])
        self._turn_index = 0
        self._chat_status = chat_status
        self._end_status = end_status
        self._end_conversation_id = end_conversation_id or str(uuid.uuid4())
        self._chat_emits_done = chat_emits_done_sentinel

        @self.app.post("/v1/internal/voice/init")
        async def _init(payload: dict):
            self.init_calls.append(payload)
            if init_status != 200:
                from fastapi import HTTPException

                raise HTTPException(status_code=init_status, detail="stub init error")
            return {
                "caller_info": {
                    "sender_identifier": payload["caller_number"],
                    "recipient_identifier": payload["dialed_number"],
                    "call_id": payload["call_id"],
                },
                "voice_id": "stub-voice",
                "speech_rate": 1.0,
                "first_message": "Hi",
                "languages": ["english"],
                "background_sound": None,
                "pronunciation_dict_id": None,
            }

        @self.app.post("/v1/chat/completions")
        async def _chat(payload: dict):
            self.chat_calls.append(payload)
            if self._chat_status != 200:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=self._chat_status, detail="stub chat error"
                )

            reply = self._turn_replies[
                min(self._turn_index, len(self._turn_replies) - 1)
            ]
            self._turn_index += 1

            emit_done = self._chat_emits_done

            async def _gen():
                # Simulate two chunks so the driver exercises its
                # accumulate-across-chunks path.
                head = reply[: len(reply) // 2] if len(reply) > 1 else reply
                tail = reply[len(reply) // 2 :] if len(reply) > 1 else ""
                for piece in (head, tail):
                    if not piece:
                        continue
                    chunk = {
                        "id": "chatcmpl-stub",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": payload["model"],
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": piece},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                if emit_done:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(_gen(), media_type="text/event-stream")

        @self.app.post("/v1/internal/voice/end-call")
        async def _end(payload: dict):
            self.end_calls.append(payload)
            if self._end_status != 200:
                from fastapi import HTTPException

                raise HTTPException(status_code=self._end_status, detail="stub end")
            return {
                "status": "success",
                "conversation_id": self._end_conversation_id,
            }


# ---------------------------------------------------------------------------
# Happy-path lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_init_is_lazy_and_fires_on_first_turn(self) -> None:
        stub = _StubApp(turn_replies=["hello there"])
        driver = HttpVoiceDriver(
            app=stub.app,
            recipient_identifier="+14155551212",
            scenario_id="sc-1",
        )

        # No network activity during construction.
        assert stub.init_calls == []
        assert stub.chat_calls == []

        result = await driver.send_turn("hi", [])

        assert result.content == "hello there"
        assert len(stub.init_calls) == 1
        assert stub.init_calls[0]["call_id"] == driver.call_id
        assert stub.init_calls[0]["dialed_number"] == "+14155551212"
        # Safety: every http_voice scenario must flag the Conversation as
        # test so downstream spec construction auto-applies eval_safety.
        assert stub.init_calls[0]["testing"] is True

        await driver.aclose()

    async def test_init_runs_only_once_across_turns(self) -> None:
        stub = _StubApp(turn_replies=["a", "b", "c"])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("t1", [])
        await driver.send_turn("t2", [])
        await driver.send_turn("t3", [])

        assert len(stub.init_calls) == 1
        assert len(stub.chat_calls) == 3

        await driver.aclose()

    async def test_call_id_is_stable_and_passed_on_every_turn(self) -> None:
        stub = _StubApp(turn_replies=["a", "b"])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("t1", [])
        await driver.send_turn("t2", [])

        init_call_id = stub.init_calls[0]["call_id"]
        turn1_caller_info = json.loads(stub.chat_calls[0]["model"])
        turn2_caller_info = json.loads(stub.chat_calls[1]["model"])

        assert init_call_id == driver.call_id
        assert turn1_caller_info["call_id"] == driver.call_id
        assert turn2_caller_info["call_id"] == driver.call_id

        await driver.aclose()

    async def test_call_id_includes_scenario_id_for_traceability(self) -> None:
        stub = _StubApp()
        driver = HttpVoiceDriver(
            app=stub.app,
            recipient_identifier="+14155551212",
            scenario_id="pick-4-combo",
        )

        assert driver.call_id.startswith("eval-pick-4-combo")

    async def test_aclose_populates_last_conversation_id(self) -> None:
        known_conv_id = str(uuid.uuid4())
        stub = _StubApp(turn_replies=["ok"], end_conversation_id=known_conv_id)
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        assert driver.last_conversation_id is None
        await driver.send_turn("hi", [])
        assert driver.last_conversation_id is None  # set only on aclose

        await driver.aclose()

        assert driver.last_conversation_id == known_conv_id
        assert len(stub.end_calls) == 1
        assert stub.end_calls[0]["call_id"] == driver.call_id

    async def test_conversation_replay_in_end_call_matches_turn_history(self) -> None:
        stub = _StubApp(turn_replies=["reply one", "reply two"])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("question one", [])
        await driver.send_turn("question two", [])
        await driver.aclose()

        replay = stub.end_calls[0]["conversation"]
        assert replay == [
            {"role": "user", "content": "question one"},
            {"role": "assistant", "content": "reply one"},
            {"role": "user", "content": "question two"},
            {"role": "assistant", "content": "reply two"},
        ]


# ---------------------------------------------------------------------------
# Idempotency / defensive shape
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_aclose_is_safe_without_send_turn(self) -> None:
        stub = _StubApp()
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.aclose()

        # Neither init nor end-call fired — nothing to clean up.
        assert stub.init_calls == []
        assert stub.end_calls == []
        assert driver.last_conversation_id is None

    async def test_aclose_is_idempotent(self) -> None:
        stub = _StubApp(turn_replies=["ok"])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("hi", [])
        await driver.aclose()
        await driver.aclose()

        assert len(stub.end_calls) == 1

    async def test_send_turn_after_aclose_raises(self) -> None:
        stub = _StubApp(turn_replies=["ok"])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("hi", [])
        await driver.aclose()

        with pytest.raises(RuntimeError, match="after aclose"):
            await driver.send_turn("too late", [])


# ---------------------------------------------------------------------------
# Error handling at each endpoint
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_init_failure_raises_and_cleans_up(self) -> None:
        stub = _StubApp(init_status=404)
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155559999")

        with pytest.raises(RuntimeError, match="voice /init failed"):
            await driver.send_turn("hi", [])

        # Client was closed, so aclose is a no-op and doesn't hit end-call.
        await driver.aclose()
        assert stub.end_calls == []

    async def test_chat_failure_raises_through_send_turn(self) -> None:
        stub = _StubApp(chat_status=500)
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        with pytest.raises(RuntimeError, match="chat /completions failed"):
            await driver.send_turn("hi", [])

        # aclose still works; end-call is still attempted and records the
        # partial conversation (none here).
        await driver.aclose()
        assert len(stub.end_calls) == 1

    async def test_end_call_failure_is_swallowed(self) -> None:
        stub = _StubApp(turn_replies=["ok"], end_status=500)
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        await driver.send_turn("hi", [])
        # No exception: aclose logs the bad response and returns.
        await driver.aclose()

        assert driver.last_conversation_id is None


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------


class TestStreamParsing:
    async def test_tolerates_missing_done_sentinel(self) -> None:
        stub = _StubApp(turn_replies=["hello world"], chat_emits_done_sentinel=False)
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        result = await driver.send_turn("hi", [])

        assert result.content == "hello world"
        await driver.aclose()

    async def test_accumulates_content_across_chunks(self) -> None:
        stub = _StubApp(turn_replies=["hello " * 10])
        driver = HttpVoiceDriver(app=stub.app, recipient_identifier="+14155551212")

        result = await driver.send_turn("hi", [])

        # Stub splits each reply into two chunks; driver should join them.
        assert result.content == "hello " * 10
        await driver.aclose()
