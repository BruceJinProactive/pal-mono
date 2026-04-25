"""Tests for tools.escalation_tools — Langfuse @observe decorator migration."""


class TestEscalationTools:
    """Covers lines 2 (@observe import), 26, 36, 48 (@observe decorators)."""

    def test_get_criteria_returns_configured_value(self):
        from tools.escalation_tools import EscalationTools

        config = {
            "settings": {
                "criteria": "Customer is angry",
                "escalated_response": "Transferring you now",
                "emergency_response": "Please call 911",
            }
        }
        tool = EscalationTools(config=config)

        assert tool.get_criteria() == "Customer is angry"

    def test_get_escalated_response_returns_configured_value(self):
        from tools.escalation_tools import EscalationTools

        config = {
            "settings": {
                "criteria": "test",
                "escalated_response": "Transferring you now",
                "emergency_response": "Please call 911",
            }
        }
        tool = EscalationTools(config=config)

        assert tool.get_escalated_response() == "Transferring you now"

    def test_get_emergency_response_returns_configured_value(self):
        from tools.escalation_tools import EscalationTools

        config = {
            "settings": {
                "criteria": "test",
                "escalated_response": "transfer",
                "emergency_response": "Please call 911",
            }
        }
        tool = EscalationTools(config=config)

        assert tool.get_emergency_response() == "Please call 911"
