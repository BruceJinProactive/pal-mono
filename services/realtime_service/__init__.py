"""
OpenAI Realtime Voice service for voice conversations.

This service provides integration with OpenAI's Realtime API for
voice-based conversations through Twilio media streams.
"""

from ._implementation import RealtimeSession, create_realtime_session

__all__ = ["RealtimeSession", "create_realtime_session"]
