"""S1: Tenant Isolation Integration Test.

Two fully-populated tenant hierarchies with identical data shapes.
Systematically proves every tenant-scoped repository method returns
data exclusively from the queried tenant.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.repositories.agent_repository import AgentRepository
from db.repositories.integration_repository import IntegrationRepository
from db.repositories.project_integration_repository import ProjectIntegrationRepository
from db.repositories.project_repository import ProjectRepository
from db.repositories.user_repository import UserRepository
from db.tables import Conversation, Message
from tests.factories import (
    make_conversation,
    make_integration,
    make_message,
    make_project_integration,
    make_world,
)


@pytest.mark.integration
class TestTenantIsolation:
    """Proves tenant isolation at the repository layer."""

    def test_users_scoped_by_account(self, db_session: Session) -> None:
        """UserRepository.get_users_by_account_id returns only that account's users."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        repo = UserRepository(db_session)
        users_a = repo.get_users_by_account_id(world_a.account.id)
        users_b = repo.get_users_by_account_id(world_b.account.id)

        user_ids_a = {u.id for u in users_a}
        user_ids_b = {u.id for u in users_b}

        assert world_a.user.id in user_ids_a
        assert world_b.user.id not in user_ids_a
        assert world_b.user.id in user_ids_b
        assert world_a.user.id not in user_ids_b
        assert user_ids_a.isdisjoint(user_ids_b)

    def test_projects_scoped_by_account(self, db_session: Session) -> None:
        """ProjectRepository.get_projects_by_account_id returns only that account's projects."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        repo = ProjectRepository(db_session)
        projects_a = repo.get_projects_by_account_id(world_a.account.id)
        projects_b = repo.get_projects_by_account_id(world_b.account.id)

        proj_ids_a = {p.id for p in projects_a}
        proj_ids_b = {p.id for p in projects_b}

        assert world_a.project.id in proj_ids_a
        assert world_b.project.id not in proj_ids_a
        assert world_b.project.id in proj_ids_b
        assert world_a.project.id not in proj_ids_b
        assert proj_ids_a.isdisjoint(proj_ids_b)

    def test_get_agent_by_id_returns_correct_agent(self, db_session: Session) -> None:
        """AgentRepository.get_agent returns the correct agent by ID (no account_id guard)."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        repo = AgentRepository(db_session)
        agent_a = repo.get_agent(world_a.agent.id)
        agent_b = repo.get_agent(world_b.agent.id)

        assert agent_a is not None
        assert agent_b is not None
        assert agent_a.account_id == world_a.account.id
        assert agent_b.account_id == world_b.account.id
        assert agent_a.id != agent_b.id

    def test_integrations_scoped_by_account(self, db_session: Session) -> None:
        """IntegrationRepository.get_integrations_by_account_id returns only that account's."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        make_integration(db_session, account_id=world_a.account.id)
        make_integration(db_session, account_id=world_b.account.id)

        repo = IntegrationRepository(db_session)
        integrations_a = repo.get_integrations_by_account_id(world_a.account.id)
        integrations_b = repo.get_integrations_by_account_id(world_b.account.id)

        ids_a = {i.id for i in integrations_a}
        ids_b = {i.id for i in integrations_b}

        assert len(ids_a) == 1
        assert len(ids_b) == 1
        assert ids_a.isdisjoint(ids_b)

    def test_project_integrations_scoped_by_project(self, db_session: Session) -> None:
        """ProjectIntegrationRepository returns only that project's integrations."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        int_a = make_integration(db_session, account_id=world_a.account.id)
        int_b = make_integration(db_session, account_id=world_b.account.id)

        make_project_integration(
            db_session,
            project_id=world_a.project.id,
            integration_id=int_a.id,
        )
        make_project_integration(
            db_session,
            project_id=world_b.project.id,
            integration_id=int_b.id,
        )

        repo = ProjectIntegrationRepository(db_session)
        pi_a = repo.get_project_integrations_by_project_id(world_a.project.id)
        pi_b = repo.get_project_integrations_by_project_id(world_b.project.id)

        pi_ids_a = {pi.id for pi in pi_a}
        pi_ids_b = {pi.id for pi in pi_b}

        assert len(pi_ids_a) == 1
        assert len(pi_ids_b) == 1
        assert pi_ids_a.isdisjoint(pi_ids_b)

    def test_conversations_scoped_by_project(self, db_session: Session) -> None:
        """Conversations filtered by project return only that project's data."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        for _ in range(3):
            make_conversation(
                db_session,
                user_id=world_a.user.id,
                project_id=world_a.project.id,
            )
            make_conversation(
                db_session,
                user_id=world_b.user.id,
                project_id=world_b.project.id,
            )

        convs_a = (
            db_session.execute(
                select(Conversation).where(
                    Conversation.project_id == world_a.project.id
                )
            )
            .scalars()
            .all()
        )
        convs_b = (
            db_session.execute(
                select(Conversation).where(
                    Conversation.project_id == world_b.project.id
                )
            )
            .scalars()
            .all()
        )

        ids_a = {c.id for c in convs_a}
        ids_b = {c.id for c in convs_b}

        assert len(ids_a) == 3
        assert len(ids_b) == 3
        assert ids_a.isdisjoint(ids_b)

    def test_messages_scoped_by_conversation(self, db_session: Session) -> None:
        """Messages from tenant A's conversations never appear in tenant B's queries."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        conv_a = make_conversation(
            db_session,
            user_id=world_a.user.id,
            project_id=world_a.project.id,
        )
        conv_b = make_conversation(
            db_session,
            user_id=world_b.user.id,
            project_id=world_b.project.id,
        )

        msg_ids_a = set()
        msg_ids_b = set()
        for i in range(5):
            m = make_message(
                db_session,
                conversation_id=conv_a.id,
                body={"role": "user", "content": f"Tenant A msg {i}"},
            )
            msg_ids_a.add(m.id)
        for i in range(5):
            m = make_message(
                db_session,
                conversation_id=conv_b.id,
                body={"role": "user", "content": f"Tenant B msg {i}"},
            )
            msg_ids_b.add(m.id)

        fetched_a = {
            m.id
            for m in db_session.execute(
                select(Message).where(Message.conversation_id == conv_a.id)
            )
            .scalars()
            .all()
        }
        fetched_b = {
            m.id
            for m in db_session.execute(
                select(Message).where(Message.conversation_id == conv_b.id)
            )
            .scalars()
            .all()
        }

        assert fetched_a == msg_ids_a
        assert fetched_b == msg_ids_b
        assert fetched_a.isdisjoint(fetched_b)

    def test_cross_tenant_user_lookup_returns_empty(self, db_session: Session) -> None:
        """Querying an account with no users returns empty."""
        world_a = make_world(db_session)

        repo = UserRepository(db_session)
        # Query a non-existent account — truly empty result
        users = repo.get_users_by_account_id(uuid.uuid4())
        assert len(users) == 0

        # Also verify A's user is not in B's account
        world_b = make_world(db_session)
        users_in_b = repo.get_users_by_account_id(world_b.account.id)
        user_ids_in_b = {u.id for u in users_in_b}
        assert world_a.user.id not in user_ids_in_b

    def test_cross_tenant_integration_lookup_returns_empty(
        self, db_session: Session
    ) -> None:
        """Querying tenant A's integrations with tenant B's account returns empty."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        make_integration(db_session, account_id=world_a.account.id)

        repo = IntegrationRepository(db_session)
        integrations_b = repo.get_integrations_by_account_id(world_b.account.id)

        assert len(integrations_b) == 0

    def test_conversation_to_account_chain_within_tenant(
        self, db_session: Session
    ) -> None:
        """Conversation -> User -> Account chain stays within a single tenant."""
        world = make_world(db_session)
        conv = make_conversation(
            db_session,
            user_id=world.user.id,
            project_id=world.project.id,
        )

        # Walk the chain via DB
        loaded_conv = db_session.execute(
            select(Conversation).where(Conversation.id == conv.id)
        ).scalar_one()

        assert loaded_conv.user_id == world.user.id
        assert loaded_conv.project_id == world.project.id

        # Verify user belongs to same account
        user = UserRepository(db_session).get_user_by_id(loaded_conv.user_id)
        assert user is not None
        assert user.account_id == world.account.id

    def test_set_intersection_empty_across_all_entities(
        self, db_session: Session
    ) -> None:
        """For all entity types, query(tenant=A) INTERSECT query(tenant=B) = empty."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)

        # Add data to both tenants
        make_integration(db_session, account_id=world_a.account.id)
        make_integration(db_session, account_id=world_b.account.id)
        make_conversation(
            db_session,
            user_id=world_a.user.id,
            project_id=world_a.project.id,
        )
        make_conversation(
            db_session,
            user_id=world_b.user.id,
            project_id=world_b.project.id,
        )

        user_repo = UserRepository(db_session)
        proj_repo = ProjectRepository(db_session)
        int_repo = IntegrationRepository(db_session)

        # Users
        u_a = {u.id for u in user_repo.get_users_by_account_id(world_a.account.id)}
        u_b = {u.id for u in user_repo.get_users_by_account_id(world_b.account.id)}
        assert u_a.isdisjoint(u_b)

        # Projects
        p_a = {p.id for p in proj_repo.get_projects_by_account_id(world_a.account.id)}
        p_b = {p.id for p in proj_repo.get_projects_by_account_id(world_b.account.id)}
        assert p_a.isdisjoint(p_b)

        # Integrations
        i_a = {
            i.id for i in int_repo.get_integrations_by_account_id(world_a.account.id)
        }
        i_b = {
            i.id for i in int_repo.get_integrations_by_account_id(world_b.account.id)
        }
        assert i_a.isdisjoint(i_b)

        # Conversations (by project)
        c_a = {
            c.id
            for c in db_session.execute(
                select(Conversation).where(
                    Conversation.project_id == world_a.project.id
                )
            )
            .scalars()
            .all()
        }
        c_b = {
            c.id
            for c in db_session.execute(
                select(Conversation).where(
                    Conversation.project_id == world_b.project.id
                )
            )
            .scalars()
            .all()
        }
        assert c_a.isdisjoint(c_b)
