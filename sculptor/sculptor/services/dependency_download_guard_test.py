"""The unit-test suite must never download a managed binary from a remote source.

These tests verify the conftest guard (``_block_managed_binary_downloads``): without
an explicit ``@pytest.mark.allow_dependency_downloads`` opt-out, the dependency-management
service's download manager is mocked out, so a real remote download can never happen and
startup auto-provisioning is a no-op.
"""

import pytest

from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.dependency_management_service import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService


def test_managed_install_raises_instead_of_downloading(
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """A managed install attempted from an unmarked unit test raises loudly rather than fetching."""
    service = DependencyManagementService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("dependency_management_service")
    )
    for tool in (Dependency.PI, Dependency.CLAUDE):
        with pytest.raises(AssertionError, match="allow_dependency_downloads"):
            service.install_managed(tool)


def test_service_collection_startup_does_not_auto_install(
    test_service_collection: CompleteServiceCollection,
) -> None:
    """Standing up the full service collection auto-installs nothing — no thread, no network."""
    dms = test_service_collection.dependency_management_service
    assert dms._installing == {}
    assert dms._install_thread == {}
