import builtins
from functools import cached_property
from importlib import import_module
from traceback import format_tb
from types import TracebackType
from typing import cast

from typing_extensions import TypeAliasType

from imbue_core.async_monkey_patches import EXCEPTION_LOGGED_FLAG
from imbue_core.fixed_traceback import FixedTraceback
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.serialization_types import Serializable

JsonTypeAlias = TypeAliasType(
    "JsonTypeAlias",
    "dict[str, JsonTypeAlias] | list[JsonTypeAlias] | str | int | float | bool | None",
)


class SerializedException(SerializableModel):
    """A serializable dataclass that represents an exception"""

    exception: str
    args: "tuple[SerializedException | JsonTypeAlias, ...]"  # pyre-ignore[11]: pyre doesn't like TypeAliasType
    traceback_dict: JsonTypeAlias
    was_logged_by_log_exception: bool = False

    @classmethod
    def build(cls, exception: BaseException, traceback: TracebackType | None = None) -> "SerializedException":
        if traceback is None:
            traceback = exception.__traceback__
            assert traceback is not None, " ".join(
                (
                    "No traceback deriveable or as a concrete argument!",
                    f"You probably want to convert_to_serialized_exception in your except clause: {exception=}",
                )
            )
        return SerializedException(  # pyre-fixme[28]: pyre doesn't understand pydantic
            exception=get_fully_qualified_name_for_error(exception),
            args=tuple(_convert_serialized_exception_args(x, traceback) for x in exception.args),
            traceback_dict=FixedTraceback.from_tb(traceback).as_dict(),
            was_logged_by_log_exception=getattr(exception, EXCEPTION_LOGGED_FLAG, False),
        )

    @cached_property
    def traceback(self) -> FixedTraceback | None:
        traceback_dict = self.traceback_dict
        if traceback_dict is None:
            return None
        return FixedTraceback.from_dict(traceback_dict)

    @cached_property
    def exception_module(self) -> str:
        if "." in self.exception:
            return self.exception.rsplit(".", maxsplit=1)[0]
        return ""

    @cached_property
    def exception_type(self) -> str:
        return self.exception.rsplit(".", maxsplit=1)[-1]

    @cached_property
    def exception_class(self) -> type[BaseException]:
        if self.exception_module:
            return cast(type[BaseException], getattr(import_module(self.exception_module), self.exception_type, None))
        else:
            return cast(type[BaseException], getattr(builtins, self.exception_type, None))

    def construct_instance(self) -> BaseException:
        try:
            exception = self.exception_class(*cast(tuple[Serializable, ...], self.args))
        except TypeError as e:
            message_with_arg_info = (
                f"Failed to construct exception {self.exception_class} with args {self.args}.",
                "Ensure that the exception class is serializable and can be constructed with the provided args.",
            )
            raise TypeError(" ".join(message_with_arg_info)) from e

        try:
            setattr(exception, EXCEPTION_LOGGED_FLAG, True)
        except AttributeError:
            # We could not set the flag correctly
            pass

        return exception

    def as_formatted_traceback(self) -> str:
        if self.traceback is None:
            traceback_str = ""
        else:
            # pyre-ignore[6]: pyre doesn't know that FixedTraceback is a traceback (since it's not a TracebackType)
            traceback_str = "".join(format_tb(self.traceback))
        return f"Traceback (most recent call last):\n{traceback_str}\n{self.exception}: {self.args}"


def _convert_serialized_exception_args(error: Serializable, traceback: TracebackType | None = None) -> JsonTypeAlias:
    if isinstance(error, BaseException):
        return SerializedException.build(error, traceback=traceback)
    elif isinstance(error, (list, tuple)):
        return tuple(_convert_serialized_exception_args(x, traceback) for x in error)
    elif isinstance(error, (str, int, float, bool, dict, type(None))):
        return error
    # Convert non-JSON-serializable types (e.g. bytes from process output) to str
    # to avoid pydantic ValidationError when building SerializedException.
    return str(error)


def get_fully_qualified_name_for_error(e: BaseException) -> str:
    if e.__class__.__module__ == "builtins":
        return e.__class__.__name__
    return f"{e.__class__.__module__}.{e.__class__.__name__}"
