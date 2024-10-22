import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from db.repositories.project_repository import ProjectRepository


def get_project(db: Session, project_id: uuid.UUID):
    project_repository = ProjectRepository(db)
    return project_repository.get_project(project_id)


def update_project_config(
    db: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = ProjectRepository(db)
    project_repository.update_project_config(project_id=project_id, config=config)


def replace_project_channel_identifiers(
    db: Session, project_id: uuid.UUID, channel_identifiers: List[str]
) -> None:
    project_repository = ProjectRepository(db)
    project_repository.replace_project_channel_identifiers(
        project_id=project_id, channel_identifiers=channel_identifiers
    )


def replace_project_config(
    db: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = ProjectRepository(db)
    project_repository.replace_project_config(project_id=project_id, config=config)
