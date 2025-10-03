from typing import Annotated
from typing import Any
from typing import Union
from typing import get_args
from typing import get_origin


def extract_leaf_types(type_annotation: Any, is_everything_expanded: bool = False) -> tuple[type, ...]:
    """
    Recursively extract leaf types from a type annotation.

    When `is_everything_expanded` is True, expand all types having arguments, including Lists, Tuples, Generators, etc.
    Otherwise, only expand Union and Annotated types.

    Example:
        _extract_leaf_types(Annotated[Union[int, None], Tag("foo")]) == (int, None)
    """
    origin = get_origin(type_annotation)
    args = get_args(type_annotation)
    if origin is Annotated:
        return extract_leaf_types(args[0], is_everything_expanded=is_everything_expanded)
    elif (
        origin is Union
        or (hasattr(type_annotation, "__class__") and type_annotation.__class__.__name__ == "UnionType")
        or (origin is not None and is_everything_expanded)
    ):
        result = []
        for arg in args:
            result.extend(extract_leaf_types(arg, is_everything_expanded=is_everything_expanded))
        return tuple(result)
    else:
        return (type_annotation,)
