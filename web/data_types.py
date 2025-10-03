from pathlib import Path
from typing import Annotated

from pydantic import EmailStr
from pydantic import Tag

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.sculptor.state.messages import LLMModel
from imbue_core.sculptor.user_config import UserConfig
from sculptor.interfaces.agents.v1.agent import DiffArtifact
from sculptor.interfaces.agents.v1.agent import LogsArtifact
from sculptor.interfaces.agents.v1.agent import MessageTypes
from sculptor.interfaces.agents.v1.agent import SuggestionsArtifact
from sculptor.interfaces.agents.v1.agent import TodoListArtifact
from sculptor.interfaces.agents.v1.agent import UsageArtifact
from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.interfaces.environments.v1.provider_status import ProviderStatusTypes
from sculptor.primitives.ids import UserReference
from sculptor.web.derived import TaskInterface


class RequestModel(SerializableModel):
    pass


class StartTaskRequest(RequestModel):
    prompt: str
    interface: str = TaskInterface.TERMINAL.value
    source_branch: str | None = None
    model: LLMModel
    is_including_uncommitted_changes: bool = False


class ForkTaskRequest(RequestModel):
    chat_message_id: AgentMessageID
    prompt: str
    model: LLMModel


class FixTaskRequest(RequestModel):
    description: str


class SendMessageRequest(RequestModel):
    message: str
    model: LLMModel


class MessageRequest(RequestModel):
    message: MessageTypes
    is_awaited: bool = False
    timeout_seconds: int | None = None


class SendCommandRequest(RequestModel):
    message: str
    is_included_in_context: bool


class CompactTaskMessageRequest(RequestModel):
    pass


class SystemPromptRequest(RequestModel):
    system_prompt: str


class DefaultSystemPromptRequest(RequestModel):
    default_system_prompt: str


class ArchiveTaskRequest(RequestModel):
    is_archived: bool


ArtifactDataResponse = Annotated[
    Annotated[TodoListArtifact, Tag("TodoListArtifact")]
    | Annotated[LogsArtifact, Tag("LogsArtifact")]
    | Annotated[DiffArtifact, Tag("DiffArtifact")]
    | Annotated[SuggestionsArtifact, Tag("SuggestionsArtifact")]
    | Annotated[UsageArtifact, Tag("UsageArtifact")],
    build_discriminator(),
]


class ReadFileRequest(RequestModel):
    file_path: str


class TransferRepoDecisionOption(SerializableModel):
    option: str
    # for visual indication of the option
    is_destructive: bool = False
    is_default: bool = False


class TransferRepoUserChoice(SerializableModel):
    decision_id: str
    choice: str


# TODO: consider if these can be somewhat strongly typed
#       or available to frontend *before* the request
class TransferRepoDecision(SerializableModel):
    id: str
    title: str
    message: str
    detailed_context: str | None = None
    options: tuple[TransferRepoDecisionOption, ...]

    def resolve_user_choice(self, user_choices: list[TransferRepoUserChoice] | None) -> str | None:
        if user_choices is None:
            return None
        for choice in user_choices:
            if choice.decision_id == self.id:
                return choice.choice
        return None


class TransferRepoAssumptions(SerializableModel):
    local_branch: str


class TransferRepoBaseRequest(RequestModel):
    target_local_branch: str
    include_uncommitted_changes: bool = False

    assumptions: TransferRepoAssumptions
    user_choices: list[TransferRepoUserChoice] | None = None

    @property
    def user_choice_by_decision_id(self) -> dict[str, str] | None:
        if self.user_choices:
            return {choice.decision_id: choice.choice for choice in self.user_choices}
        return None


class TransferRepoBaseResponse(SerializableModel):
    success: bool

    notices: list[str] | None = None
    missing_decisions: list[TransferRepoDecision] | None = None


class TransferFromTaskToLocalRequest(TransferRepoBaseRequest):
    pass


class TransferFromTaskToLocalResponse(TransferRepoBaseResponse):
    # TODO: a bit of a stop-gap to get better posthog tracking
    reached_operation_or_failure_label: str | None = None


class TransferFromLocalToTaskRequest(TransferRepoBaseRequest):
    pass


class TransferFromLocalToTaskResponse(TransferRepoBaseResponse):
    pass


class GitCommitAndPushRequest(RequestModel):
    commit_message: str


class FeedbackRequest(RequestModel):
    feedback_type: str  # "positive" or "negative"
    comment: str | None = None
    issue_type: str | None = None


class RepoInfo(SerializableModel):
    """Repository information"""

    repo_path: Path
    current_branch: str
    recent_branches: list[str]
    project_id: ProjectID
    num_uncommitted_changes: int


class UserInfo(SerializableModel):
    """Current user information"""

    user_reference: UserReference | None
    email: EmailStr | None


class ProviderStatusInfo(SerializableModel):
    """Status information for a single provider"""

    provider: ProviderTag
    status: ProviderStatusTypes


class InitializeGitRepoRequest(RequestModel):
    """Request to initialize a directory as a git repository"""

    project_path: str


class CreateInitialCommitRequest(RequestModel):
    """Request to create an initial commit in a new git repository"""

    project_path: str


class ProjectInitializationRequest(RequestModel):
    """Request to initialize a new project"""

    project_path: str


class ConfigStatusResponse(SerializableModel):
    """Response for config status check"""

    has_email: bool
    has_api_key: bool
    has_privacy_consent: bool
    has_telemetry_level: bool


class EmailConfigRequest(RequestModel):
    """Request to save user email configuration"""

    user_email: EmailStr
    full_name: str | None = None


class PrivacyConfigRequest(RequestModel):
    """Request to save privacy/telemetry settings"""

    telemetry_level: int  # 2-4
    is_repo_backup_enabled: bool = False


class UpdateUserConfigRequest(RequestModel):
    user_config: UserConfig


class DependenciesStatus(SerializableModel):
    """Status of required dependencies"""

    docker_installed: bool
    docker_running: bool
    mutagen_installed: bool
    git_installed: bool
