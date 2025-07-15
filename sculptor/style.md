# `sculptor` style guide

This document describes the style guide for all `python` code in the `sculptor` application.

For the style guide for the frontend code, see the [../frontend/docs/style.md](../frontend/docs/style.md) file.

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

# Comments

## Conventions

- Use `# FIXME:` for tasks that must be done before merging.  If you want to merge something with a FIXME, create a ticket for it and link to it in the comment.
- Use `# TODO:` for tasks that could be done in the future, and are effectively just a description of the current state of the code.
- Use `# LOCAL_ONLY`: for information that only applies to the server when it is running locally on a user's machine.

# Testing

## Preventing flaky tests

Flaky tests are very annoying, and waste a lot of developer time.

Fundamentally, they are caused by non-determinism in the code being tested (e.g., random numbers, timeouts, concurrency, etc.)

Most of these sources of non-determinism can (and should) be eliminated from most tests:
- For randomness, tests should be given a fixed seed.
- For time, tests should use generally use special timing primitives that control how the process perceives time.
- For environment variables, tests should use a fixed set of environment variables.

For concurrency, tests should be designed to run in a deterministic manner, e.g., by using a single-threaded event loop or by controlling the concurrency level of the code being tested.

When concurrency is required for the behavior under test, the tests should be written to take "actions", eg, atomic operations that know when they are complete.
This should be done at all levels of the application, from the UI down to the database.
All "actions" should have timeouts, and all failures should be surfaced.

Machine / system level differences can still cause differences or failures, but with the above handled,
they are at least much less likely (especially when the computational infrastructure is the same, e.g., all tests run on the same CI system, and can be retried when there are transient failures.)

## Integration tests

### Specifying which behavior to test

All of our integration testing should flow from the top level specification of user stories.

Please write user stories in the `./docs/user_stories.md` file,
then use those to create integration test plans in `./docs/test_plans/`

The user stories, test plans, and figma designs should be sufficient to fully specify the desired behavior of the product.
