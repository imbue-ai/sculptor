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

# Comments

## Conventions

- Use `# FIXME:` for tasks that must be done before merging.  If you want to merge something with a FIXME, create a ticket for it and link to it in the comment.
- Use `# TODO:` for tasks that could be done in the future, and are effectively just a description of the current state of the code.
- Use `# LOCAL_ONLY`: for information that only applies to the server when it is running locally on a user's machine.

# Testing

better style of testing -- need to *know* that the action completed
    and that's something that goes through the whole application, really
    it ought to be designed to be "transactional" even at these different layers
    is "functional" or something...  you're taking this action that has an effect and then returns once that effect is complete
    and those are the ONLY things that you can do...
could we get a less flaky pattern for tests? (to know when an action has been done)
    yes, we can, finally!
    is all about "actions" -- everything should be expressed that way the entire way down
    in the UI, you take some action, it has some result
    built into the whole architecture of the software that all actions are functions that are SYNC until they are done!!  (even if the implementation is different)
    and there are sometimes different bits, sure -- like if you kick off a background task, it will *logically* take some time before being complete, but the *action* is "start the task"
    and we can have a *separate* action for "start a task and wait for it to finish", which is different
for better testing: everything you do is an action, all actions have timeouts, all actions can fail, all failures must be reported
    time bounds on everything (so that if the heartbeat is going, nothing can be "stuck")
for better testing: enable "deterministic" mode as we build this
    specifically, reduce concurrent connections and processing down to basically 1 everywhere (ex: in task processor, in request handling, etc)
    remove randomness, etc
testing -- should flow from the top level specification of user stories and become test specs and then tests!
    then that (plus the figma designs) is ALL that we need in order to specify the behavior of the product
    well, and interfaces, routes, etc
    but we can be a lot clearer about what the specification is -- it's basically *in the repo* and we WANT that (otherwise LLM cannot understand it and extend and implement)
