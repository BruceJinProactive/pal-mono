"""Synthetic caller for voice evaluation.

Joins a LiveKit room as an RTC participant, publishes TTS audio for each
user turn, waits for the agent to respond, and returns the call_id used
to collect results from the database.

This implements the ``SyntheticCallerFactory`` protocol defined in
``_voice_eval_runner.py``.

Usage::

    from services.eval_service._synthetic_caller import SyntheticCaller

    caller = SyntheticCaller(livekit_url="wss://lk.example.com")
    call_id = await caller.run_call(
        room_info=room_info,
        caller_token="jwt-token",
        turns=["Hello", "I'd like to order a pizza"],
        voice_profile=profile,
        tts_engine=engine,
        call_id="eval-abc123",
    )

Requires the ``livekit`` package (livekit-rtc): ``pip install livekit``
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from livekit import rtc
from pal_agents.evals.voice.room_orchestrator import RoomInfo
from pal_agents.evals.voice.tts_engine import TTSEngine, VoiceProfile

from utils.log import logger

_DEFAULT_PAUSE_BETWEEN_TURNS_S = 1.5
_DEFAULT_AGENT_RESPONSE_TIMEOUT_S = 30.0
_AUDIO_SAMPLE_RATE = 48000
_AUDIO_NUM_CHANNELS = 1
_FRAME_DURATION_MS = 20.0


@dataclass
class SyntheticCaller:
    """LiveKit RTC participant that simulates a caller for voice eval.

    Connects to a room, publishes TTS audio tracks for each user turn,
    and waits for the agent to finish responding before proceeding to
    the next turn.
    """

    livekit_url: str
    pause_between_turns_s: float = _DEFAULT_PAUSE_BETWEEN_TURNS_S
    agent_response_timeout_s: float = _DEFAULT_AGENT_RESPONSE_TIMEOUT_S
    _room: rtc.Room = field(default_factory=rtc.Room, init=False, repr=False)

    async def run_call(
        self,
        room_info: RoomInfo,
        caller_token: str,
        turns: list[str],
        voice_profile: VoiceProfile,
        tts_engine: TTSEngine,
        call_id: str,
    ) -> str:
        """Run a synthetic call in the given room.

        Connects as a participant, publishes TTS audio for each turn,
        waits for agent responses, and returns the call_id.

        Args:
            room_info: LiveKit room to connect to.
            caller_token: JWT token for the synthetic caller participant.
                The token includes ``sip.callID`` in participant attributes.
            turns: List of user turn texts to speak via TTS.
            voice_profile: TTS voice configuration for this persona.
            tts_engine: TTS engine instance for speech synthesis.
            call_id: Pre-generated call ID (already embedded in the token).

        Returns:
            The call_id (same as input).
        """

        try:
            await self._room.connect(room_info.livekit_url, caller_token)
            logger.info(
                "Synthetic caller connected to room",
                extra={
                    "room_name": room_info.room_name,
                    "call_id": call_id,
                },
            )

            # Wait for the agent to join before speaking
            await self._wait_for_agent()

            # Create audio source and track for publishing TTS audio
            audio_source = rtc.AudioSource(
                sample_rate=_AUDIO_SAMPLE_RATE,
                num_channels=_AUDIO_NUM_CHANNELS,
            )
            track = rtc.LocalAudioTrack.create_audio_track(
                "synthetic-caller-audio", audio_source
            )
            await self._room.local_participant.publish_track(track)

            logger.info(
                "Synthetic caller audio track published",
                extra={
                    "room_name": room_info.room_name,
                    "num_turns": len(turns),
                },
            )

            # Wait for the agent's greeting to finish before speaking
            logger.debug("Waiting for agent greeting to finish")
            await self._wait_for_agent_response()
            await asyncio.sleep(self.pause_between_turns_s)

            # Run each turn: synthesize → publish audio → wait for agent
            for i, turn_text in enumerate(turns):
                logger.debug(
                    "Synthetic caller speaking turn %d/%d",
                    i + 1,
                    len(turns),
                    extra={"turn_text": turn_text[:100]},
                )

                await self._speak_turn(
                    turn_text, audio_source, tts_engine, voice_profile
                )

                # Wait for agent to finish responding before next turn
                if i < len(turns) - 1:
                    await self._wait_for_agent_response()
                    await asyncio.sleep(self.pause_between_turns_s)

            # After last turn, wait for agent's final response
            await self._wait_for_agent_response()

            logger.info(
                "Synthetic caller completed all turns",
                extra={
                    "room_name": room_info.room_name,
                    "call_id": call_id,
                    "turns_completed": len(turns),
                },
            )

        finally:
            await self._disconnect()

        return call_id

    async def _wait_for_agent(self) -> None:
        """Wait until at least one non-local participant (the agent) joins."""
        if self._room.remote_participants:
            return

        agent_joined: asyncio.Event = asyncio.Event()

        @self._room.on("participant_connected")
        def _on_participant_connected(
            participant: rtc.RemoteParticipant,
        ) -> None:
            logger.debug("Participant connected: %s", participant.identity)
            agent_joined.set()

        try:
            await asyncio.wait_for(
                agent_joined.wait(),
                timeout=self.agent_response_timeout_s,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                "Agent did not join the room within "
                f"{self.agent_response_timeout_s}s"
            )
        finally:
            self._room.off("participant_connected", _on_participant_connected)

    async def _speak_turn(
        self,
        text: str,
        audio_source: rtc.AudioSource,
        tts_engine: TTSEngine,
        voice_profile: VoiceProfile,
    ) -> None:
        """Synthesize text via TTS and publish audio frames to the room."""
        samples_per_frame = int(_AUDIO_SAMPLE_RATE * _FRAME_DURATION_MS / 1000.0)

        async for chunk in tts_engine.synthesize_streaming(
            text, profile=voice_profile, frame_duration_ms=_FRAME_DURATION_MS
        ):
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=_AUDIO_SAMPLE_RATE,
                num_channels=_AUDIO_NUM_CHANNELS,
                samples_per_channel=samples_per_frame,
            )
            await audio_source.capture_frame(frame)

    async def _wait_for_agent_response(self) -> None:
        """Wait for the agent to finish speaking.

        Detects agent speech by monitoring active speakers. When the agent
        appears in the active speakers list and then disappears (or the
        timeout is reached), this method returns.
        """
        agent_started_speaking = asyncio.Event()
        agent_stopped_speaking = asyncio.Event()
        agent_is_speaking = False

        @self._room.on("active_speakers_changed")
        def _on_speakers_changed(
            speakers: list[rtc.Participant],
        ) -> None:
            nonlocal agent_is_speaking

            local_sid = self._room.local_participant.sid
            agent_speaking_now = any(s.sid != local_sid for s in speakers)

            if agent_speaking_now and not agent_is_speaking:
                agent_is_speaking = True
                agent_started_speaking.set()
            elif not agent_speaking_now and agent_is_speaking:
                agent_is_speaking = False
                agent_stopped_speaking.set()

        try:
            # Wait for agent to start speaking (or timeout)
            try:
                await asyncio.wait_for(
                    agent_started_speaking.wait(),
                    timeout=self.agent_response_timeout_s,
                )
            except asyncio.TimeoutError:
                logger.debug("Agent did not start speaking within timeout")
                return

            # Wait for agent to stop speaking (or timeout)
            try:
                await asyncio.wait_for(
                    agent_stopped_speaking.wait(),
                    timeout=self.agent_response_timeout_s,
                )
            except asyncio.TimeoutError:
                logger.debug("Agent did not stop speaking within timeout")
        finally:
            self._room.off("active_speakers_changed", _on_speakers_changed)

    async def _disconnect(self) -> None:
        """Disconnect from the room gracefully."""
        try:
            await self._room.disconnect()
        except Exception:
            logger.exception("Error disconnecting synthetic caller from room")
