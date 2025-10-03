"""Test utilities for working with Docker images."""

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.database.core import create_new_engine
from sculptor.database.utils import convert_sqlite_url_to_read_only_format
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService


def get_task_image_ids(database_url: str, task_id: str) -> list[str]:
    """
    Get all Docker image IDs associated with a task.

    Returns a list of image IDs in chronological order (oldest to newest),
    including historical snapshots and the current state image.
    """
    # Set up database connection
    data_model_service = SQLDataModelService()
    database_url_read_only = convert_sqlite_url_to_read_only_format(database_url)
    data_model_service._engine = create_new_engine(database_url_read_only)
    data_model_service._is_read_only = True
    data_model_service.start()

    image_ids = []

    try:
        with data_model_service.open_task_transaction() as transaction:
            # Get the task
            task = transaction.get_task(task_id)
            if not task:
                logger.error("Task {} not found", task_id)
                return []

            # Get historical images from snapshot messages
            saved_messages = transaction.get_messages_for_task(task_id)
            for message in saved_messages:
                if isinstance(message.message, AgentSnapshotRunnerMessage):
                    if isinstance(message.message.image, LocalDockerImage):
                        image_id = message.message.image.image_id
                        image_ids.append(image_id)

    finally:
        data_model_service.stop()

    logger.debug("Found {} images for task {}", len(image_ids), task_id)
    return image_ids


def get_project_id_for_task(database_url: str, task_id: str) -> ProjectID:
    # Set up database connection
    data_model_service = SQLDataModelService()
    database_url_read_only = convert_sqlite_url_to_read_only_format(database_url)
    data_model_service._engine = create_new_engine(database_url_read_only)
    data_model_service._is_read_only = True
    data_model_service.start()

    try:
        with data_model_service.open_task_transaction() as transaction:
            # Get the task
            task = transaction.get_task(task_id)
            if not task:
                raise Exception("Task {} not found", task_id)
            return task.project_id

    finally:
        data_model_service.stop()


def get_all_task_images(database_url: str) -> dict[str, list[str]]:
    """
    Get all Docker image IDs for all tasks in the database.

    Returns a dictionary mapping task IDs to lists of image IDs.
    """
    # Set up database connection
    data_model_service = SQLDataModelService()
    database_url_read_only = convert_sqlite_url_to_read_only_format(database_url)
    data_model_service._engine = create_new_engine(database_url_read_only)
    data_model_service._is_read_only = True
    data_model_service.start()

    task_images = {}

    try:
        with data_model_service.open_task_transaction() as transaction:
            # Get all tasks
            tasks = transaction.get_all_tasks()

            for task in tasks:
                task_id = task.object_id
                image_ids = []

                # Get historical images from snapshot messages
                saved_messages = transaction.get_messages_for_task(task_id)
                for message in saved_messages:
                    if isinstance(message.message, AgentSnapshotRunnerMessage):
                        if isinstance(message.message.image, LocalDockerImage):
                            image_id = message.message.image.image_id
                            if image_id not in image_ids:
                                image_ids.append(image_id)

                if image_ids:
                    task_images[str(task_id)] = image_ids

    finally:
        data_model_service.stop()

    logger.debug("Found images for {} tasks", len(task_images))
    return task_images
