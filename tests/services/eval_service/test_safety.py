"""Tests for services/eval_service/_safety.py."""

from __future__ import annotations

from pal_agents.spec import AdoraSpec, PromptSpec, Spec, ToastSpec

from services.eval_service._safety import apply_eval_safety


def _make_spec(
    *,
    toast: ToastSpec | None = None,
    adora: AdoraSpec | None = None,
) -> Spec:
    return Spec(
        prompt=PromptSpec(instructions="You are a test agent."),
        toast=toast or ToastSpec(),
        adora=adora or AdoraSpec(),
    )


class TestToastSafety:
    def test_flips_submit_orders_when_enabled_and_submitting(self) -> None:
        toast = ToastSpec(
            enabled=True,
            restaurant_guid="rg",
            takeout_dining_option_guid="td",
            menu_data={"items": []},
            submit_orders=True,
        )
        spec = _make_spec(toast=toast)

        apply_eval_safety(spec)

        assert spec.toast.submit_orders is False

    def test_noop_when_toast_already_price_only(self) -> None:
        toast = ToastSpec(
            enabled=True,
            restaurant_guid="rg",
            takeout_dining_option_guid="td",
            menu_data={"items": []},
            submit_orders=False,
        )
        spec = _make_spec(toast=toast)

        apply_eval_safety(spec)

        assert spec.toast.submit_orders is False

    def test_noop_when_toast_disabled(self) -> None:
        # Even if submit_orders=True slipped through, a disabled Toast
        # provider is inert; we should not touch it.
        toast = ToastSpec(enabled=False, submit_orders=True)
        spec = _make_spec(toast=toast)

        apply_eval_safety(spec)

        assert spec.toast.enabled is False
        assert spec.toast.submit_orders is True


class TestAdoraSafety:
    def test_forces_force_payment_link_when_enabled(self) -> None:
        adora = AdoraSpec(
            enabled=True, menu_data={"items": []}, force_payment_link=False
        )
        spec = _make_spec(adora=adora)

        apply_eval_safety(spec)

        assert spec.adora.force_payment_link is True

    def test_noop_when_adora_already_force_payment_link(self) -> None:
        adora = AdoraSpec(
            enabled=True, menu_data={"items": []}, force_payment_link=True
        )
        spec = _make_spec(adora=adora)

        apply_eval_safety(spec)

        assert spec.adora.force_payment_link is True

    def test_noop_when_adora_disabled(self) -> None:
        # Disabled Adora provider is inert; don't mutate.
        adora = AdoraSpec(enabled=False, force_payment_link=False)
        spec = _make_spec(adora=adora)

        apply_eval_safety(spec)

        assert spec.adora.enabled is False
        assert spec.adora.force_payment_link is False


class TestCombined:
    def test_no_providers_enabled_is_noop(self) -> None:
        spec = _make_spec()
        apply_eval_safety(spec)  # does not raise

    def test_both_providers_enabled_are_hardened(self) -> None:
        toast = ToastSpec(
            enabled=True,
            restaurant_guid="rg",
            takeout_dining_option_guid="td",
            menu_data={"items": []},
            submit_orders=True,
        )
        adora = AdoraSpec(
            enabled=True, menu_data={"items": []}, force_payment_link=False
        )
        spec = _make_spec(toast=toast, adora=adora)

        apply_eval_safety(spec)

        assert spec.toast.submit_orders is False
        assert spec.adora.force_payment_link is True
