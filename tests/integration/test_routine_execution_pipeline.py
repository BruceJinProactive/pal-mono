"""S9: Routine Execution Pipeline.

Tests the routine entity hierarchy: Routine -> Items, Schedules,
Executions, Submissions, ItemResponses at the DB layer.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables import (
    Routine,
    RoutineExecution,
    RoutineItem,
    RoutineItemResponse,
    RoutineSchedule,
    RoutineSubmission,
)
from db.tables.types import (
    ExecutionStatus,
    ItemResponseStatus,
    RoutineCategory,
    RoutineFrequency,
    SubmissionStatus,
)
from tests.factories import (
    make_agent,
    make_project,
    make_routine,
    make_routine_execution,
    make_routine_item,
    make_routine_item_response,
    make_routine_schedule,
    make_routine_submission,
    make_world,
)


@pytest.mark.integration
class TestRoutineExecutionPipeline:
    def test_routine_with_items_created(self, db_session: Session) -> None:
        """Routine with 3 items persists correctly."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)

        items = []
        for i in range(3):
            item = make_routine_item(
                db_session,
                routine_id=routine.id,
                name=f"Item {i}",
                sort_order=i,
            )
            items.append(item)

        loaded_items = (
            db_session.execute(
                select(RoutineItem).where(RoutineItem.routine_id == routine.id)
            )
            .scalars()
            .all()
        )

        assert len(loaded_items) == 3
        names = {item.name for item in loaded_items}
        assert names == {"Item 0", "Item 1", "Item 2"}

    def test_schedule_creation(self, db_session: Session) -> None:
        """Schedule is created with correct fields."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)
        schedule = make_routine_schedule(db_session, routine_id=routine.id)

        result = db_session.execute(
            select(RoutineSchedule).where(RoutineSchedule.id == schedule.id)
        ).scalar_one()

        assert result.routine_id == routine.id
        assert result.frequency == RoutineFrequency.daily
        assert result.timezone == "America/Los_Angeles"
        assert result.days_of_week == [0, 1, 2, 3, 4]

    def test_execution_linked_to_routine_and_schedule(
        self, db_session: Session
    ) -> None:
        """Execution is linked to both routine and schedule."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)
        schedule = make_routine_schedule(db_session, routine_id=routine.id)
        execution = make_routine_execution(
            db_session,
            routine_id=routine.id,
            schedule_id=schedule.id,
        )

        result = db_session.execute(
            select(RoutineExecution).where(RoutineExecution.id == execution.id)
        ).scalar_one()

        assert result.routine_id == routine.id
        assert result.schedule_id == schedule.id
        assert result.status == ExecutionStatus.pending

    def test_submission_lifecycle(self, db_session: Session) -> None:
        """Submission with item responses persists correctly."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)
        item = make_routine_item(db_session, routine_id=routine.id)
        schedule = make_routine_schedule(db_session, routine_id=routine.id)
        execution = make_routine_execution(
            db_session,
            routine_id=routine.id,
            schedule_id=schedule.id,
        )
        submission = make_routine_submission(db_session, execution_id=execution.id)
        response = make_routine_item_response(
            db_session,
            submission_id=submission.id,
            routine_item_id=item.id,
        )

        # Verify chain
        loaded_sub = db_session.execute(
            select(RoutineSubmission).where(RoutineSubmission.id == submission.id)
        ).scalar_one()
        assert loaded_sub.execution_id == execution.id
        assert loaded_sub.status == SubmissionStatus.draft

        loaded_resp = db_session.execute(
            select(RoutineItemResponse).where(RoutineItemResponse.id == response.id)
        ).scalar_one()
        assert loaded_resp.submission_id == submission.id
        assert loaded_resp.routine_item_id == item.id
        assert loaded_resp.status == ItemResponseStatus.pending

    def test_project_scoping(self, db_session: Session) -> None:
        """Two projects with separate routines, query returns only that project's."""
        world = make_world(db_session)
        agent_b = make_agent(db_session, account_id=world.account.id)
        project_b = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=agent_b.id,
        )

        make_routine(db_session, project_id=world.project.id, name="Routine A")
        make_routine(db_session, project_id=project_b.id, name="Routine B")

        routines_a = (
            db_session.execute(
                select(Routine).where(Routine.project_id == world.project.id)
            )
            .scalars()
            .all()
        )
        routines_b = (
            db_session.execute(
                select(Routine).where(Routine.project_id == project_b.id)
            )
            .scalars()
            .all()
        )

        assert len(routines_a) == 1
        assert routines_a[0].name == "Routine A"
        assert len(routines_b) == 1
        assert routines_b[0].name == "Routine B"

        ids_a = {r.id for r in routines_a}
        ids_b = {r.id for r in routines_b}
        assert ids_a.isdisjoint(ids_b)

    def test_execution_status_transitions(self, db_session: Session) -> None:
        """Execution status: pending -> in_progress -> completed."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)
        schedule = make_routine_schedule(db_session, routine_id=routine.id)
        execution = make_routine_execution(
            db_session,
            routine_id=routine.id,
            schedule_id=schedule.id,
            status=ExecutionStatus.pending,
        )

        # Transition to in_progress
        execution.status = ExecutionStatus.in_progress
        db_session.flush()

        result = db_session.execute(
            select(RoutineExecution).where(RoutineExecution.id == execution.id)
        ).scalar_one()
        assert result.status == ExecutionStatus.in_progress

        # Transition to completed
        execution.status = ExecutionStatus.completed
        db_session.flush()

        result = db_session.execute(
            select(RoutineExecution).where(RoutineExecution.id == execution.id)
        ).scalar_one()
        assert result.status == ExecutionStatus.completed

    def test_submission_status_transitions(self, db_session: Session) -> None:
        """Submission status: draft -> submitted -> completed."""
        world = make_world(db_session)
        routine = make_routine(db_session, project_id=world.project.id)
        schedule = make_routine_schedule(db_session, routine_id=routine.id)
        execution = make_routine_execution(
            db_session,
            routine_id=routine.id,
            schedule_id=schedule.id,
        )
        submission = make_routine_submission(
            db_session,
            execution_id=execution.id,
            status=SubmissionStatus.draft,
        )

        # Draft -> submitted
        submission.status = SubmissionStatus.submitted
        db_session.flush()

        result = db_session.execute(
            select(RoutineSubmission).where(RoutineSubmission.id == submission.id)
        ).scalar_one()
        assert result.status == SubmissionStatus.submitted

        # Submitted -> approved
        submission.status = SubmissionStatus.approved
        db_session.flush()

        result = db_session.execute(
            select(RoutineSubmission).where(RoutineSubmission.id == submission.id)
        ).scalar_one()
        assert result.status == SubmissionStatus.approved

    def test_routine_category_persists(self, db_session: Session) -> None:
        """Routine category is persisted correctly."""
        world = make_world(db_session)
        routine = make_routine(
            db_session,
            project_id=world.project.id,
            category=RoutineCategory.custom,
        )

        result = db_session.execute(
            select(Routine).where(Routine.id == routine.id)
        ).scalar_one()
        assert result.category == RoutineCategory.custom
        assert result.is_active is True
