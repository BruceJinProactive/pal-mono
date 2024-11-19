import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

import db


def get_project(session: Session, project_id: uuid.UUID):
    project_repository = db.ProjectRepository(session)
    return project_repository.get_project(project_id)


def update_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.update_project_config(project_id=project_id, config=config)


def replace_project_channel_identifiers(
    session: Session, project_id: uuid.UUID, channel_identifiers: List[str]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.replace_project_channel_identifiers(
        project_id=project_id, channel_identifiers=channel_identifiers
    )


def replace_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.replace_project_config(project_id=project_id, config=config)
