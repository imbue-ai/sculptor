# `sculptor` style guide

This document describes the style guide for all `python` code in the `sculptor` application.

For the style guide for the frontend code, see the [web/frontend/style.md](./web/frontend/style.md) file.

# Data Types

"data types" should be defined as `python` classes using the `pydantic` library.

data type classes should all inherit from `imbue_core.pydantic_serialization.SerializableModel` (if serializable) or `imbue_core.pydantic_serialization.FrozenModel` (if internal)

Both types are defined with `frozen=True`, so all data types should be considered immutable.

To change the value of an instance of a data type, call the `evolve` method of that object to create an updated copy with the new value.
```python
from imbue_core.pydantic_serialization import SerializableModel


class SomeType(SerializableModel):
    data: int

obj = SomeType(data=42)
new_obj = obj.evolve(obj.ref().data, 7)
```

Because all objects are immutable, most functions that deal with data types should be defined as top-level function
(rather than methods of the data type class itself.)

Define such functions in the same file as the data type class (after the class definition.)

Type definitions for other languages (e.g., `TypeScript`, `SQL`, etc.) should be generated from `python` definitions.
