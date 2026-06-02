from pydantic import Field

from sculptor.foundation.pydantic_serialization import SerializableModel


class CustomActionGroup(SerializableModel):
    """A named group for organizing custom actions."""

    id: str
    name: str
    order: int


class CustomAction(SerializableModel):
    """A reusable one-click action button that sends a predefined prompt."""

    id: str
    name: str
    prompt: str
    auto_submit: bool = True
    group_id: str | None = None
    order: int = 0


class CustomActionsConfig(SerializableModel):
    """Configuration for all custom actions and their groups."""

    actions: list[CustomAction] = Field(default_factory=list)
    groups: list[CustomActionGroup] = Field(default_factory=list)
