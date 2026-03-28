from __future__ import annotations

from services.agent_service._fingerprint import compute_agent_fingerprint

_BASE_CONFIG: dict = {"model": "gpt-4o", "temperature": 0.7}
_BASE_PROMPT: list[tuple[str, str]] = [
    ("system", "You are a helpful assistant."),
    ("context", "Restaurant: Palona Cafe"),
]


def test_deterministic() -> None:
    """Same inputs must produce identical fingerprints on every call."""
    result_a = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    result_b = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    assert result_a == result_b


def test_prompt_sensitivity() -> None:
    """Changing prompt content must change the prompt_fingerprint."""
    _, fp_original, _ = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    different_prompt: list[tuple[str, str]] = [
        ("system", "You are a strict assistant."),
        ("context", "Restaurant: Palona Cafe"),
    ]
    _, fp_changed, _ = compute_agent_fingerprint(_BASE_CONFIG, different_prompt)
    assert fp_original != fp_changed


def test_config_sensitivity() -> None:
    """Changing config_dict must change the agent_fingerprint."""
    af_original, _, _ = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    different_config: dict = {"model": "gpt-4o-mini", "temperature": 0.7}
    af_changed, _, _ = compute_agent_fingerprint(different_config, _BASE_PROMPT)
    assert af_original != af_changed


def test_knowledge_snapshot_included() -> None:
    """Adding a knowledge_snapshot_id must change the agent_fingerprint."""
    af_without, _, _ = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    af_with, _, _ = compute_agent_fingerprint(
        _BASE_CONFIG, _BASE_PROMPT, knowledge_snapshot_id="snap-abc123"
    )
    assert af_without != af_with


def test_returns_config_dict_unchanged() -> None:
    """The third return value must be the same config_dict passed in."""
    config: dict = {"model": "gpt-4o", "temperature": 0.5}
    _, _, returned_config = compute_agent_fingerprint(config, _BASE_PROMPT)
    assert returned_config is config


def test_fingerprints_are_sha256_hex() -> None:
    """Fingerprints must be 64-character lowercase hex strings."""
    af, pf, _ = compute_agent_fingerprint(_BASE_CONFIG, _BASE_PROMPT)
    assert len(af) == 64
    assert len(pf) == 64
    assert af == af.lower()
    assert pf == pf.lower()
