"""What an agent in a jj workspace is told about its bookmarks, read without running jj or git."""

from typing import Callable
from typing import Protocol
from typing import runtime_checkable

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import DataModelService


class JjStackBookmarks(FrozenModel):
    """The bookmarks on a jj workspace's stack, as the jj poller last published them."""

    working_copy_change_id: str
    bookmarks: tuple[str, ...] = Field(description="Every local bookmark on the stack, nearest the working copy first")
    primary_bookmark: str | None
    unbookmarked_revision_count: int = Field(
        description="Described revisions above the primary bookmark; every described revision when there is none"
    )


class JjBookmarkFacts(FrozenModel):
    requested_bookmark: str | None = Field(
        description="The bookmark Sculptor creates for the workspace's work; None when the workspace requested none"
    )
    stack: JjStackBookmarks | None = Field(description="None until the jj poller has scanned the workspace")


@runtime_checkable
class JjBookmarkFactsProvider(Protocol):
    def get_jj_bookmark_facts(self) -> JjBookmarkFacts: ...


class DefaultJjBookmarkFactsProvider:
    def __init__(
        self,
        workspace_id: WorkspaceID,
        data_model_service: DataModelService,
        read_cached_stack_bookmarks: Callable[[WorkspaceID], JjStackBookmarks | None],
    ) -> None:
        self._workspace_id = workspace_id
        self._data_model_service = data_model_service
        self._read_cached_stack_bookmarks = read_cached_stack_bookmarks

    def get_jj_bookmark_facts(self) -> JjBookmarkFacts:
        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspace = transaction.get_workspace(self._workspace_id)
        return JjBookmarkFacts(
            requested_bookmark=None if workspace is None else workspace.requested_branch_name,
            stack=self._read_cached_stack_bookmarks(self._workspace_id),
        )
