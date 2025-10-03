from abc import ABC
from typing import Annotated

from pydantic import Field
from pydantic import Tag

from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator


class ProviderStatus(SerializableModel, ABC):
    message: str
    details: dict | None = Field(default=None)
    object_type: str


class OkStatus(ProviderStatus):
    object_type: str = Field(default="OkStatus")


class DownStatus(ProviderStatus):
    object_type: str = Field(default="DownStatus")


ProviderStatusTypes = Annotated[
    Annotated[OkStatus, Tag("OkStatus")] | Annotated[DownStatus, Tag("DownStatus")],
    build_discriminator(),
]
