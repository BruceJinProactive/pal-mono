"""Tests for the adora capability move merge behavior.

PR 2a of the adora capability split (PAL-11022). These tests pin the
`PromptFactoryV2._merge_capabilities` behavior at three states relevant
to the move of `create_order_adora` from `ordering.yaml` into
`adora.yaml`:

1. Failure mode (regression catcher): the action present in both
   `ordering` and `adora` YAML simultaneously - would dual-emit. PR 2a
   removes the action from `ordering.yaml`, so this state should never
   ship; the test exists to flag any future regression.
2. Deploy-window state: PR 2a deployed (action in `adora` YAML only) but
   PR 2b migration not yet run (DB override still keyed to `ordering`
   capability). The DB override ships as a DB-only action under
   `<ordering>`; the `adora` YAML default ships under `<adora>` (brief
   dual emit limited to agents that have a DB override).
3. Final state: PR 2a + PR 2b both landed. The DB override is repointed
   to `adora`; the override replaces the YAML default. Single emit
   under `<adora>`.
"""

from services.prompt_service.prompts_v2 import Action, Capability, PromptFactoryV2


def _capability(identifier: str, priority: int, actions: list) -> Capability:
    return Capability(
        identifier=identifier,
        priority=priority,
        enabled=True,
        actions=actions,
    )


def _action(name: str, instruction: str) -> Action:
    return Action(
        action=name,
        instruction=instruction,
        channel="ALL",
        priority=10,
        enabled=True,
    )


class TestAdoraMoveMergeBehavior:
    def setup_method(self) -> None:
        self.factory = PromptFactoryV2()

    def test_regression_action_in_both_yamls_dual_emits(self) -> None:
        """Regression catcher: if `create_order_adora` ever appears in
        both `ordering.yaml` and `adora.yaml` simultaneously, the merged
        structure surfaces it under both capabilities. PR 2a removes it
        from `ordering.yaml`, so this should never be the shipped state.
        """
        defaults = {
            "ordering": _capability(
                "ordering",
                20,
                [_action("create_order_adora", "ordering YAML text")],
            ),
            "adora": _capability(
                "adora",
                95,
                [_action("create_order_adora", "adora YAML text")],
            ),
        }
        merged = self.factory._merge_capabilities(defaults, {})

        ordering_actions = [a.action for a in merged["ordering"].actions]
        adora_actions = [a.action for a in merged["adora"].actions]
        assert "create_order_adora" in ordering_actions
        assert "create_order_adora" in adora_actions

    def test_deploy_window_override_under_ordering_default_under_adora(
        self,
    ) -> None:
        """PR 2a deployed, PR 2b migration not yet run.

        `ordering.yaml` no longer carries `create_order_adora`.
        `adora.yaml` carries it as a YAML default. The customized
        agent's DB override is still keyed to the `ordering` capability.

        Per the merge logic, the DB override under `ordering` is added
        as a DB-only action (no matching YAML default to replace) and
        ships under `<ordering>`. The `adora` YAML default ships under
        `<adora>`. The action appears twice during this window for
        customized agents only.
        """
        defaults = {
            "ordering": _capability("ordering", 20, []),
            "adora": _capability(
                "adora",
                95,
                [_action("create_order_adora", "adora YAML default")],
            ),
        }
        db_overrides = {
            "ordering": _capability(
                "ordering",
                20,
                [_action("create_order_adora", "customer override text")],
            ),
        }
        merged = self.factory._merge_capabilities(defaults, db_overrides)

        ordering_actions = {a.action: a.instruction for a in merged["ordering"].actions}
        adora_actions = {a.action: a.instruction for a in merged["adora"].actions}
        assert ordering_actions == {"create_order_adora": "customer override text"}
        assert adora_actions == {"create_order_adora": "adora YAML default"}

    def test_final_state_override_repointed_to_adora_single_emit(self) -> None:
        """PR 2a and PR 2b both landed.

        `adora.yaml` carries the YAML default; the customer's DB
        override is now keyed to the `adora` capability. The merge
        replaces the YAML default with the override under `<adora>`,
        and `<ordering>` no longer carries the action.
        """
        defaults = {
            "ordering": _capability("ordering", 20, []),
            "adora": _capability(
                "adora",
                95,
                [_action("create_order_adora", "adora YAML default")],
            ),
        }
        db_overrides = {
            "adora": _capability(
                "adora",
                95,
                [_action("create_order_adora", "customer override text")],
            ),
        }
        merged = self.factory._merge_capabilities(defaults, db_overrides)

        ordering_actions = [a.action for a in merged["ordering"].actions]
        adora_actions = {a.action: a.instruction for a in merged["adora"].actions}
        assert "create_order_adora" not in ordering_actions
        assert adora_actions == {"create_order_adora": "customer override text"}
