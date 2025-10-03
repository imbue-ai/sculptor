from pydantic import model_validator

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.v1.agent import RunID


class CheckRunOutputLocation(FrozenModel):
    """
    See README.md in this folder for documentation on the layout of checks data.
    """

    # contains the path within the container where the agent data is stored
    root_data_path: str
    # the task for which we are running this check
    task_id: TaskID
    # the user message id with which this check is associated
    user_message_id: AgentMessageID
    # randomly generated id for the run of the check
    run_id: RunID
    # mostly here because the check can be None if validation failed, and we need to key off of this
    check_name: str

    @model_validator(mode="before")
    @classmethod
    def _validator(cls, data: dict) -> dict:
        """Allow construction from either a dict or a path string."""
        full_path: str | None = data.pop("_full_path", None)
        if full_path:
            assert len(data) == 0
            # Parse the string path
            parts = full_path.rstrip("/").split("/")

            try:
                checks_idx = parts.index("checks")
            except ValueError:
                raise ValueError(f"Path must contain '/checks/' segment: {data}")

            remaining = parts[checks_idx + 1 :]
            if len(remaining) != 3:
                raise ValueError(f"Expected 3 segments after '/checks/', got {len(remaining)}")

            return {
                "root_data_path": "/".join(parts[: checks_idx - 1]),
                "task_id": parts[checks_idx - 1],
                "user_message_id": remaining[0],
                "check_name": remaining[1],
                "run_id": remaining[2],
            }

        return data

    @classmethod
    def build_from_folder(cls, folder: str) -> "CheckRunOutputLocation":
        # noinspection PyArgumentList
        return cls(_full_path=folder)

    def to_message_folder(self) -> str:
        return f"{self.root_data_path}/{self.task_id}/checks/{self.user_message_id}"

    def to_check_folder(self) -> str:
        return f"{self.to_message_folder()}/{self.check_name}"

    def to_run_folder(self) -> str:
        return f"{self.to_check_folder()}/{self.run_id}"
