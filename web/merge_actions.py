import enum

import pydantic
from fastapi import HTTPException
from loguru import logger

from imbue_core.pydantic_serialization import MutableModel
from imbue_core.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.v1.agent import ManualSyncMergeIntoAgentNoticeLabel
from sculptor.services.git_repo_service.api import GitRepoStatus
from sculptor.services.git_repo_service.api import ReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import RemoteWritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError


def _get_consistent_status_or_raise_http_exception(repo: ReadOnlyGitRepo, repo_name: str) -> GitRepoStatus:
    status = repo.get_current_status()
    if status.is_in_intermediate_state:
        raise HTTPException(
            status_code=409,
            detail=f"{repo_name} is in an inconsistent state: {status.describe()}",
        )
    return status


class MergeActionNoticeKind(enum.StrEnum):
    SUCCESS = "SUCCESS"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class MergeActionNotice(SerializableModel):
    label: ManualSyncMergeIntoAgentNoticeLabel
    message: str
    kind: MergeActionNoticeKind = pydantic.Field(default=MergeActionNoticeKind.INFO)
    details: str | None = None


class MergeActionResult(MutableModel):
    notices: list[MergeActionNotice] = pydantic.Field(default=[])
    success: bool = False


def merge_into_agent(
    task_repo: RemoteWritableGitRepo,
    user_repo: LocalReadOnlyGitRepo,
    local_branch_name: str,
) -> MergeActionResult:
    result = MergeActionResult(success=False)

    task_repo_status = _get_consistent_status_or_raise_http_exception(task_repo, "Agent repository")
    if not task_repo_status.is_clean_and_safe_to_operate_on:
        result.notices.append(
            MergeActionNotice(
                kind=MergeActionNoticeKind.WARNING,
                label=ManualSyncMergeIntoAgentNoticeLabel.AGENT_UNCOMMITTED_CHANGES,
                message="Agent repository has uncommited changes",
                details=task_repo_status.describe(),
            )
        )

    # check if we are pushing a checked out branch, we should verify it's in a good state
    if local_branch_name == user_repo.get_current_git_branch():
        user_repo_status = _get_consistent_status_or_raise_http_exception(user_repo, "Local repository")
        if not user_repo_status.files.are_clean_including_untracked:
            result.notices.append(
                MergeActionNotice(
                    kind=MergeActionNoticeKind.INFO,
                    label=ManualSyncMergeIntoAgentNoticeLabel.LOCAL_UNCOMMITTED_CHANGES,
                    message="Your local repository has uncommitted changes which will be ignored.",
                    details=user_repo_status.describe(),
                )
            )

    try:
        head_to_push = user_repo.get_branch_head_commit_hash(branch_name=local_branch_name)
    except GitRepoError as e:
        result.notices.append(
            MergeActionNotice(
                kind=MergeActionNoticeKind.ERROR,
                label=ManualSyncMergeIntoAgentNoticeLabel.LOCAL_BRANCH_NOT_FOUND,
                message=f"Branch {local_branch_name} was not found.",
                details=str(e.stderr),
            )
        )
        return result

    logger.debug(
        "Attempting to push commit {} from branch {} to the task repository",
        head_to_push,
        local_branch_name,
    )

    remote_tag_ref = f"refs/tags/sculptor-merge-source-{head_to_push}"
    try:
        push_output = user_repo.push_ref_to_remote(
            remote=str(task_repo.get_repo_url()),
            local_ref=head_to_push,
            remote_ref=remote_tag_ref,
            is_forced=True,
        )
        result.notices.append(
            MergeActionNotice(
                kind=MergeActionNoticeKind.SUCCESS,
                label=ManualSyncMergeIntoAgentNoticeLabel.PUSH_TO_AGENT_SUCCEEDED,
                message=f"Pushed {local_branch_name}@{head_to_push[:6]} into the Agent's repository",
                details=push_output,
            )
        )
    except GitRepoError as e:
        result.notices.append(
            MergeActionNotice(
                kind=MergeActionNoticeKind.ERROR,
                label=ManualSyncMergeIntoAgentNoticeLabel.PUSH_TO_AGENT_ERROR,
                message=f"Pushing commit {head_to_push} into the Agent's repository failed",
                details=str(e.stderr),
            )
        )
        return result

    try:
        # simulating what we expect the output of `git fmt-merge-msg` to be so that the merge looks like local
        # moving to `git fmt-merge-msg` would give a user a chance to control the merge message but would required
        # one more git call roundtrip that may or may not fail. Something we can revisit later.
        merge_message_if_commit = f"Merge branch '{local_branch_name}' of {user_repo.repo_path}"
        merge_result = task_repo.merge_from_ref(remote_tag_ref, commit_message=merge_message_if_commit)
    except GitRepoError as e:
        result.notices.append(
            MergeActionNotice(
                kind=MergeActionNoticeKind.ERROR,
                label=ManualSyncMergeIntoAgentNoticeLabel.MERGE_INTO_AGENT_ERROR,
                message="Merge operation failed",
                details=str(e.stderr),
            )
        )
        return result

    if not merge_result.is_merged:
        if task_repo.is_merge_in_progress:
            result.notices.append(
                MergeActionNotice(
                    kind=MergeActionNoticeKind.WARNING,
                    label=ManualSyncMergeIntoAgentNoticeLabel.MERGED_INTO_AGENT_IN_CONFLICT,
                    message="Merge resulted in conflicts. Have the agent abort the merge or ask it to resolve the conflicts",
                    details=merge_result.raw_output,
                )
            )
        else:
            logger.info("Merge failed without leaving conflicts, raw output: {}", merge_result.raw_output)
            result.notices.append(
                MergeActionNotice(
                    kind=MergeActionNoticeKind.WARNING,
                    label=ManualSyncMergeIntoAgentNoticeLabel.MERGE_INTO_AGENT_INCOMPLETE_ODD_EDGECASE,
                    message="Merge did not succeed but did not leave conflict behind. The task repository may have conflicting uncommitted changes. Have the agent commit them and try again.",
                    details=merge_result.raw_output,
                )
            )
        return result

    assert merge_result.is_merged
    if merge_result.was_up_to_date:
        label = ManualSyncMergeIntoAgentNoticeLabel.NO_MERGE_NEEDED
        message = "Agent's branch was up-to-date, no merge needed"
    else:
        label = ManualSyncMergeIntoAgentNoticeLabel.MERGE_COMPLETED_CLEANLY
        message = f"Merged {local_branch_name}@{head_to_push[:6]} into the Agent's branch"

    result.notices.append(
        MergeActionNotice(
            label=label,
            kind=MergeActionNoticeKind.SUCCESS,
            message=message,
            details=merge_result.raw_output,
        )
    )
    result.success = True
    return result
