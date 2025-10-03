from loguru import logger

from sculptor.services.task_service.data_types import ServiceCollectionForTask


def run_cleanup_images_task_v1(services: ServiceCollectionForTask) -> None:
    """Run the cleanup images task."""
    logger.debug("Starting Docker image cleanup process")
    deleted_images = services.environment_service.remove_stale_images()

    # Log the results
    logger.info("Docker image cleanup completed. Deleted {} images", len(deleted_images))
    if deleted_images:
        logger.trace("Deleted image IDs: {}", deleted_images)
