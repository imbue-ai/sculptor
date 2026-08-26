import functools
import threading
from typing import Any
from typing import TypeVar
from typing import cast

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Discriminator
from pydantic import Json
from pydantic.alias_generators import to_camel

from sculptor.foundation.nested_evolver import _Evolver
from sculptor.foundation.nested_evolver import chill
from sculptor.foundation.nested_evolver import evolver
from sculptor.foundation.serialization_types import Serializable

# Imported defensively: pydantic may relocate its internals on a major version bump. If so, the
# memoization below is left uninstalled (the regression test fails loudly) rather than the app
# crashing at import time.
try:
    import pydantic._internal._fields as _pydantic_internal_fields
except ImportError:
    _pydantic_internal_fields = None  # type: ignore[assignment]

T = TypeVar("T", bound=BaseModel)
V = TypeVar("V")

_threading_local = threading.local()


# Memoize pydantic's per-instantiation ``default_factory`` signature check.
#
# To decide whether a ``default_factory`` accepts the validated data, pydantic calls
# ``inspect.signature(factory)`` -- and re-runs it on *every* model instantiation, for each
# ``PrivateAttr(default_factory=...)``. Under Python 3.14, ``inspect.signature`` on a C/builtin
# callable (``dict``/``list``/``set``/``threading.Lock``/...) goes through
# ``inspect._signature_fromstr``, which copies ``sys.modules`` and builds closures that capture it --
# reference cycles only the cyclic GC can reclaim. Generated thousands of times a second
# (ShutdownEvent, ConcurrencyGroup, per-stream task views), that cyclic garbage accumulates into
# gigabytes of RSS over a session. A given factory's signature never changes, so cache the check per
# factory object; the factories are module-level singletons, so the cache stays tiny. This assumes
# pydantic's helper is a pure function of the factory -- re-verify on a pydantic upgrade.
#
# Installed defensively: if pydantic has relocated its internals (the import above) or renamed the
# helper, the cache is left uninstalled and ``pydantic_serialization_test`` fails loudly, rather than
# the app crashing on a dependency bump. An unhashable factory (e.g. a ``functools.partial``) can't
# be a cache key, so it falls back to the uncached check.
_uncached_takes_validated_data_argument = (
    getattr(_pydantic_internal_fields, "takes_validated_data_argument", None)
    if _pydantic_internal_fields is not None
    else None
)
_cached_takes_validated_data_argument = (
    functools.cache(_uncached_takes_validated_data_argument)
    if _uncached_takes_validated_data_argument is not None
    else None
)


def _memoized_takes_validated_data_argument(default_factory: Any) -> Any:
    try:
        return _cached_takes_validated_data_argument(default_factory)  # type: ignore[misc]
    except TypeError:
        # Unhashable factory (e.g. a functools.partial): skip the cache, run the original check.
        return _uncached_takes_validated_data_argument(default_factory)  # type: ignore[misc]


if _uncached_takes_validated_data_argument is not None and not getattr(
    _uncached_takes_validated_data_argument, "__sculptor_memoized__", False
):
    _memoized_takes_validated_data_argument.__sculptor_memoized__ = True  # type: ignore[attr-defined]
    _memoized_takes_validated_data_argument.cache_info = _cached_takes_validated_data_argument.cache_info  # type: ignore[attr-defined]
    _memoized_takes_validated_data_argument.cache_clear = _cached_takes_validated_data_argument.cache_clear  # type: ignore[attr-defined]
    _pydantic_internal_fields.takes_validated_data_argument = _memoized_takes_validated_data_argument  # type: ignore[missing-attribute]


class EvolvableModel:
    def evolve(self: T, attribute: V, new_value: V) -> T:
        assert _threading_local.evolved_obj is not None, ".ref() must be called before evolve"

        assert isinstance(attribute, _Evolver)
        dest_evolver: _Evolver[T] = cast(_Evolver[T], attribute)
        # the evolver's attribute-reference trick is invisible to the type system (V is really T here)
        # pyrefly: ignore [bad-argument-type]
        dest_evolver.assign(new_value)

        result = chill(_threading_local.evolved_obj)
        _threading_local.evolved_obj = None
        return result

    def ref(self: T) -> T:
        _threading_local.evolved_obj = evolver(self)
        return _threading_local.evolved_obj


class FrozenModel(EvolvableModel, BaseModel):
    """
    The base class for most internal data (that does not need to be serialized).

    We generally prefer to keep data immutable in order to avoid side effects, race conditions, etc
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=False,
    )


class MutableModel(BaseModel):
    """
    The base class for any internal data that strictly must be mutable.  Should be used sparingly.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        # FIXME: go back to preventing arbitrary types once we're done converting
        # arbitrary_types_allowed=False,
        arbitrary_types_allowed=True,
    )


class SerializableModel(EvolvableModel, BaseModel, Serializable):
    """
    The base class for all data that can be serialized to/from JSON.
    """

    model_config = ConfigDict(
        frozen=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        # any extra values will end up in the __pydantic_extra__ field
        # this is effectively required for backwards compatibility
        # IMPORTANT: note that, by default, we clear this below!  These types are ONLY for backwards compatibility
        extra="allow",
        # this is also effectively required for backwards compatibility
        arbitrary_types_allowed=True,
    )

    # this is a place where we might way to do any backwards compatibility related logic
    def model_post_init(self, context: Any) -> None:
        pydantic_extra = self.__pydantic_extra__
        assert pydantic_extra is not None
        pydantic_extra.clear()


def model_dump(obj: BaseModel, is_camel_case: bool = False) -> dict[str, Any]:
    return obj.model_dump(by_alias=is_camel_case)


def model_dump_json(obj: BaseModel | Json, is_camel_case: bool = False) -> str:
    return obj.model_dump_json(by_alias=is_camel_case)


# this is mostly here for the default cases.
# When you want to upgrade a model (and keep it backwards compatible), you can make a custom discriminator
# (eg, that looks for the old type name or converts the old class names)
def build_discriminator(
    field_name: str = "object_type", additional_types_and_string_representations: tuple[tuple[type, str], ...] = ()
) -> Discriminator:
    """
    Build a discriminator for a Pydantic tagged union.

    Args:
        field_name: The name of the field to use as the discriminator tag.
        additional_types_and_string_representations: Register additional types to the discriminator.
    """

    def discriminator(obj: T | dict) -> str:
        for model_type, string_representation in additional_types_and_string_representations:
            if isinstance(obj, model_type):
                return string_representation
        if isinstance(obj, dict):
            if field_name not in obj:
                return obj[to_camel(field_name)]
            return obj[field_name]
        return getattr(obj, field_name)

    return Discriminator(discriminator=discriminator)
