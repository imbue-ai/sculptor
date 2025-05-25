# Data Types

"data types" should be defined as `python` classes using the `pydantic` library.

data type classes should all inherit from `sculptor.core.data_types.BaseDataType`.

`BaseDataType` is defined with `frozen=True`, so all data types should be considered immutable.

To change the value of an instance of a data type, call the `evolve` method of that object to create an updated copy with the new value.
```python
```

Because all objects are immutable, most functions that deal with data types should be defined as top-level function
(rather than methods of the data type class itself.)

Define such functions in the same file as the data type class (after the class definition.)

Type definitions for other languages (e.g., `TypeScript`, `SQL`, etc.) should be generated from `python` definitions.
