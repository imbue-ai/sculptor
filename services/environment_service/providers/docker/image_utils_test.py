from imbue_core.agents.data_types.ids import TaskID
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.services.environment_service.providers.docker.image_utils import DeletionTier
from sculptor.services.environment_service.providers.docker.image_utils import _calculate_image_ids_to_delete
from sculptor.services.environment_service.providers.docker.image_utils import _classify_image_tier
from sculptor.services.environment_service.providers.docker.image_utils import _get_task_ids_by_image_id
from sculptor.services.environment_service.providers.docker.image_utils import _get_tier_by_image_id


def test_classify_deleted_task_returns_always_delete():
    task_metadata = TaskImageCleanupData(
        task_id=TaskID("tsk_01abc123def456789012345678"),
        last_image_id="image-latest",
        is_deleted=True,
        is_archived=False,
        all_image_ids=("image-1", "image-2", "image-latest"),
    )
    assert _classify_image_tier("image-1", task_metadata) == DeletionTier.ALWAYS_DELETE
    assert _classify_image_tier("image-latest", task_metadata) == DeletionTier.ALWAYS_DELETE


# def test_something_always_fails():
#     logger.info("hmmm, does this show up")
#     raise Exception("oops")


def test_classify_latest_image_on_active_task_returns_never_delete():
    task_metadata = TaskImageCleanupData(
        task_id=TaskID("tsk_01abc123def456789012345678"),
        last_image_id="image-latest",
        is_deleted=False,
        is_archived=False,
        all_image_ids=("image-1", "image-2", "image-latest"),
    )
    assert _classify_image_tier("image-latest", task_metadata) == DeletionTier.NEVER_DELETE


def test_classify_historical_image_on_active_task_returns_rarely_delete():
    task_metadata = TaskImageCleanupData(
        task_id=TaskID("tsk_01abc123def456789012345678"),
        last_image_id="image-latest",
        is_deleted=False,
        is_archived=False,
        all_image_ids=("image-1", "image-2", "image-latest"),
    )
    assert _classify_image_tier("image-1", task_metadata) == DeletionTier.RARELY_DELETE
    assert _classify_image_tier("image-2", task_metadata) == DeletionTier.RARELY_DELETE


def test_classify_historical_image_on_archived_task_returns_sometimes_delete():
    task_metadata = TaskImageCleanupData(
        task_id=TaskID("tsk_01abc123def456789012345678"),
        last_image_id="image-latest",
        is_deleted=False,
        is_archived=True,
        all_image_ids=("image-1", "image-2", "image-latest"),
    )
    assert _classify_image_tier("image-1", task_metadata) == DeletionTier.SOMETIMES_DELETE
    assert _classify_image_tier("image-2", task_metadata) == DeletionTier.SOMETIMES_DELETE


def test_classify_latest_image_on_archived_task_returns_never_delete():
    task_metadata = TaskImageCleanupData(
        task_id=TaskID("tsk_01abc123def456789012345678"),
        last_image_id="image-latest",
        is_deleted=False,
        is_archived=True,
        all_image_ids=("image-1", "image-2", "image-latest"),
    )
    assert _classify_image_tier("image-latest", task_metadata) == DeletionTier.NEVER_DELETE


def test_get_task_ids_single_task_single_image():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-1",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-1",),
        )
    }
    result = _get_task_ids_by_image_id(task_metadata_by_task_id)
    assert result == {"image-1": [TaskID("tsk_01abc123def456789012345678")]}


def test_get_task_ids_single_task_multiple_images():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-3",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-1", "image-2", "image-3"),
        )
    }
    result = _get_task_ids_by_image_id(task_metadata_by_task_id)
    assert result == {
        "image-1": [TaskID("tsk_01abc123def456789012345678")],
        "image-2": [TaskID("tsk_01abc123def456789012345678")],
        "image-3": [TaskID("tsk_01abc123def456789012345678")],
    }


def test_get_task_ids_multiple_tasks_sharing_images():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")
    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="image-2",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-1", "image-2"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="image-3",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-2", "image-3"),
        ),
    }
    result = _get_task_ids_by_image_id(task_metadata_by_task_id)
    assert result == {
        "image-1": [TaskID("tsk_01abc123def456789012345678")],
        "image-2": [TaskID("tsk_01abc123def456789012345678"), TaskID("tsk_02def456789012345678abc123")],
        "image-3": [TaskID("tsk_02def456789012345678abc123")],
    }


def test_get_tier_active_image_returns_never_delete():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-2",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-1", "image-2"),
        )
    }
    active_image_ids = ("image-1",)
    result = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)
    assert result["image-1"] == DeletionTier.NEVER_DELETE


def test_get_tier_image_shared_by_multiple_tasks_takes_lowest_tier():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")
    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="image-2",
            is_deleted=True,  # Would be ALWAYS_DELETE
            is_archived=False,
            all_image_ids=("image-1", "image-2"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="image-3",
            is_deleted=False,
            is_archived=False,  # Would be RARELY_DELETE for image-1
            all_image_ids=("image-1", "image-3"),
        ),
    }
    active_image_ids = ()
    result = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)
    assert result["image-1"] == DeletionTier.RARELY_DELETE  # Takes the lowest tier


def test_get_tier_latest_image_always_never_delete():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-2",
            is_deleted=False,
            is_archived=True,
            all_image_ids=("image-1", "image-2"),
        )
    }
    active_image_ids = ()
    result = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)
    assert result["image-1"] == DeletionTier.SOMETIMES_DELETE
    assert result["image-2"] == DeletionTier.NEVER_DELETE  # Latest image


def test_get_tier_deleted_task_with_no_sharing():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-2",
            is_deleted=True,
            is_archived=False,
            all_image_ids=("image-1", "image-2"),
        )
    }
    active_image_ids = ()
    result = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)
    assert result["image-1"] == DeletionTier.ALWAYS_DELETE
    assert result["image-2"] == DeletionTier.ALWAYS_DELETE


def test_get_tier_complex_scenario_with_all_tiers():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")
    task_id_3 = TaskID("tsk_03abc789012345678def456123")
    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="image-active-latest",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-active-old", "image-active-latest", "image-shared"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="image-archived-latest",
            is_deleted=False,
            is_archived=True,
            all_image_ids=("image-archived-old", "image-archived-latest", "image-shared"),
        ),
        task_id_3: TaskImageCleanupData(
            task_id=task_id_3,
            last_image_id="image-deleted",
            is_deleted=True,
            is_archived=False,
            all_image_ids=("image-deleted",),
        ),
    }
    active_image_ids = ("image-running",)
    result = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)

    assert result["image-active-latest"] == DeletionTier.NEVER_DELETE
    assert result["image-active-old"] == DeletionTier.RARELY_DELETE
    assert result["image-archived-latest"] == DeletionTier.NEVER_DELETE
    assert result["image-archived-old"] == DeletionTier.SOMETIMES_DELETE
    assert result["image-deleted"] == DeletionTier.ALWAYS_DELETE
    assert result["image-shared"] == DeletionTier.RARELY_DELETE  # Shared by active task


def test_calculate_image_ids_to_delete_no_images():
    task_metadata_by_task_id = {}
    active_image_ids = ()
    existing_image_ids = ()
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    assert result == ()


def test_calculate_image_ids_to_delete_all_active_images():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-2",
            is_deleted=True,  # Would normally be deleted
            is_archived=False,
            all_image_ids=("image-1", "image-2"),
        )
    }
    active_image_ids = ("image-1", "image-2")  # Both images are active
    existing_image_ids = ("image-1", "image-2")
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    assert result == ()  # No images should be deleted since they're all active


def test_calculate_image_ids_to_delete_respects_minimum_tier():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")
    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="image-latest",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("image-old", "image-latest"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="image-archived-latest",
            is_deleted=False,
            is_archived=True,
            all_image_ids=("image-archived-old", "image-archived-latest"),
        ),
    }
    active_image_ids = ()
    existing_image_ids = ("image-old", "image-latest", "image-archived-old", "image-archived-latest")

    # With NEVER_DELETE minimum, only images above NEVER_DELETE are deleted
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    assert set(result) == {"image-old", "image-archived-old"}  # RARELY_DELETE and SOMETIMES_DELETE

    # With RARELY_DELETE minimum, only SOMETIMES_DELETE and above are deleted
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.RARELY_DELETE
    )
    assert set(result) == {"image-archived-old"}  # Only SOMETIMES_DELETE

    # With SOMETIMES_DELETE minimum, nothing gets deleted (no ALWAYS_DELETE images)
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.SOMETIMES_DELETE
    )
    assert result == ()


def test_calculate_image_ids_to_delete_only_existing_images():
    task_id = TaskID("tsk_01abc123def456789012345678")
    task_metadata_by_task_id = {
        task_id: TaskImageCleanupData(
            task_id=task_id,
            last_image_id="image-3",
            is_deleted=True,  # All images should be ALWAYS_DELETE
            is_archived=False,
            all_image_ids=("image-1", "image-2", "image-3"),
        )
    }
    active_image_ids = ()
    existing_image_ids = ("image-1", "image-3")  # image-2 doesn't exist
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    assert set(result) == {"image-1", "image-3"}  # Only existing images are returned


def test_calculate_image_ids_to_delete_complex_scenario():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")
    task_id_3 = TaskID("tsk_03abc789012345678def456123")

    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="active-latest",
            is_deleted=False,
            is_archived=False,
            all_image_ids=("active-old", "active-latest", "shared"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="archived-latest",
            is_deleted=False,
            is_archived=True,
            all_image_ids=("archived-old", "archived-latest", "shared"),
        ),
        task_id_3: TaskImageCleanupData(
            task_id=task_id_3,
            last_image_id="deleted-latest",
            is_deleted=True,
            is_archived=False,
            all_image_ids=("deleted-old", "deleted-latest"),
        ),
    }

    active_image_ids = ("running",)  # One image has a running container
    existing_image_ids = (
        "active-old",
        "active-latest",
        "archived-old",
        "archived-latest",
        "deleted-old",
        "deleted-latest",
        "shared",
        "running",
    )

    # Test with NEVER_DELETE minimum
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    # Should delete: active-old (RARELY), archived-old (SOMETIMES), deleted-old and deleted-latest (ALWAYS), shared (RARELY)
    assert set(result) == {"active-old", "archived-old", "deleted-old", "deleted-latest", "shared"}

    # Test with RARELY_DELETE minimum
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.RARELY_DELETE
    )
    # Should delete: archived-old (SOMETIMES), deleted-old and deleted-latest (ALWAYS)
    assert set(result) == {"archived-old", "deleted-old", "deleted-latest"}

    # Test with SOMETIMES_DELETE minimum
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.SOMETIMES_DELETE
    )
    # Should delete: deleted-old and deleted-latest (ALWAYS)
    assert set(result) == {"deleted-old", "deleted-latest"}

    # Test with ALWAYS_DELETE minimum (nothing gets deleted)
    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.ALWAYS_DELETE
    )
    assert result == ()


def test_calculate_image_ids_to_delete_shared_images_take_lowest_tier():
    task_id_1 = TaskID("tsk_01abc123def456789012345678")
    task_id_2 = TaskID("tsk_02def456789012345678abc123")

    task_metadata_by_task_id = {
        task_id_1: TaskImageCleanupData(
            task_id=task_id_1,
            last_image_id="task1-latest",
            is_deleted=True,  # Deleted task
            is_archived=False,
            all_image_ids=("shared-image", "task1-latest"),
        ),
        task_id_2: TaskImageCleanupData(
            task_id=task_id_2,
            last_image_id="shared-image",  # This is the latest for task2
            is_deleted=False,
            is_archived=False,
            all_image_ids=("shared-image",),
        ),
    }

    active_image_ids = ()
    existing_image_ids = ("shared-image", "task1-latest")

    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    # shared-image is NEVER_DELETE (latest for task2), task1-latest is ALWAYS_DELETE
    assert set(result) == {"task1-latest"}


def test_calculate_image_ids_to_delete_empty_task_metadata():
    # No tasks exist, so no images should be deleted
    task_metadata_by_task_id = {}
    active_image_ids = ()
    existing_image_ids = ("orphan-1", "orphan-2", "orphan-3")

    result = _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, DeletionTier.NEVER_DELETE
    )
    assert result == ()  # No task metadata means no images to delete
