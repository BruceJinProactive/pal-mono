"""S6: POS Tool Credential Isolation.

Proves that POS integration credentials are scoped per project.
Project A's Toast credentials never leak to Project B's queries.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.repositories.integration_repository import IntegrationRepository
from db.repositories.project_integration_repository import ProjectIntegrationRepository
from db.tables.integration import Integration
from db.tables.types import IntegrationProvider, IntegrationType
from tests.factories import (
    make_agent,
    make_integration,
    make_project,
    make_project_integration,
    make_world,
)


@pytest.mark.integration
class TestPosCredentialIsolation:
    def test_project_sees_only_own_integrations(self, db_session: Session) -> None:
        """Each project's integration query returns only its own records."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        int_a = make_integration(
            db_session,
            account_id=world.account.id,
            provider=IntegrationProvider.toast,
            secret_key="toast-secret-A",
        )
        int_b = make_integration(
            db_session,
            account_id=world.account.id,
            provider=IntegrationProvider.toast,
            secret_key="toast-secret-B",
        )

        make_project_integration(
            db_session,
            project_id=world.project.id,
            integration_id=int_a.id,
        )
        make_project_integration(
            db_session,
            project_id=project_b.id,
            integration_id=int_b.id,
        )

        repo = ProjectIntegrationRepository(db_session)
        pi_a = repo.get_project_integrations_by_project_id(world.project.id)
        pi_b = repo.get_project_integrations_by_project_id(project_b.id)

        assert len(pi_a) == 1
        assert len(pi_b) == 1
        assert pi_a[0].integration_id == int_a.id
        assert pi_b[0].integration_id == int_b.id

    def test_cross_project_query_returns_empty(self, db_session: Session) -> None:
        """Querying Project A's integrations with Project B's ID returns empty."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        int_a = make_integration(db_session, account_id=world.account.id)
        make_project_integration(
            db_session,
            project_id=world.project.id,
            integration_id=int_a.id,
        )

        repo = ProjectIntegrationRepository(db_session)
        pi_b = repo.get_project_integrations_by_project_id(project_b.id)
        assert len(pi_b) == 0

    def test_account_scoped_integration_isolation(self, db_session: Session) -> None:
        """Account A's integration not visible when querying Account B."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        make_integration(
            db_session,
            account_id=world_a.account.id,
            secret_key="secret-account-A",
        )

        repo = IntegrationRepository(db_session)
        integrations_b = repo.get_integrations_by_account_id(world_b.account.id)
        assert len(integrations_b) == 0

    def test_different_providers_per_project(self, db_session: Session) -> None:
        """Project A has Toast, Project B has Square — each returns correct provider."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        int_toast = make_integration(
            db_session,
            account_id=world.account.id,
            provider=IntegrationProvider.toast,
            integration_type=IntegrationType.pos,
        )
        int_square = make_integration(
            db_session,
            account_id=world.account.id,
            provider=IntegrationProvider.square,
            integration_type=IntegrationType.pos,
        )

        make_project_integration(
            db_session,
            project_id=world.project.id,
            integration_id=int_toast.id,
        )
        make_project_integration(
            db_session,
            project_id=project_b.id,
            integration_id=int_square.id,
        )

        repo = ProjectIntegrationRepository(db_session)
        pi_a = repo.get_project_integrations_by_project_id(world.project.id)
        pi_b = repo.get_project_integrations_by_project_id(project_b.id)

        # Verify the linked integration's provider
        linked_a = db_session.execute(
            select(Integration).where(Integration.id == pi_a[0].integration_id)
        ).scalar_one()
        linked_b = db_session.execute(
            select(Integration).where(Integration.id == pi_b[0].integration_id)
        ).scalar_one()

        assert linked_a.provider == IntegrationProvider.toast
        assert linked_b.provider == IntegrationProvider.square

    def test_credential_fields_isolated(self, db_session: Session) -> None:
        """Secret keys from one project's integration don't leak to another."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        make_integration(
            db_session,
            account_id=world_a.account.id,
            secret_key="SECRET_A_TOAST",
        )
        make_integration(
            db_session,
            account_id=world_b.account.id,
            secret_key="SECRET_B_SQUARE",
        )

        repo = IntegrationRepository(db_session)

        # Account A sees only its secret
        a_integrations = repo.get_integrations_by_account_id(world_a.account.id)
        assert len(a_integrations) == 1
        assert a_integrations[0].secret_key == "SECRET_A_TOAST"

        # Account B sees only its secret
        b_integrations = repo.get_integrations_by_account_id(world_b.account.id)
        assert len(b_integrations) == 1
        assert b_integrations[0].secret_key == "SECRET_B_SQUARE"

    def test_set_intersection_invariant(self, db_session: Session) -> None:
        """Integration IDs for project A INTERSECT project B = empty set."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        for proj in [world.project, project_b]:
            integration = make_integration(db_session, account_id=world.account.id)
            make_project_integration(
                db_session,
                project_id=proj.id,
                integration_id=integration.id,
            )

        repo = ProjectIntegrationRepository(db_session)
        ids_a = {
            pi.id
            for pi in repo.get_project_integrations_by_project_id(world.project.id)
        }
        ids_b = {
            pi.id for pi in repo.get_project_integrations_by_project_id(project_b.id)
        }

        assert len(ids_a) == 1
        assert len(ids_b) == 1
        assert ids_a.isdisjoint(ids_b)
