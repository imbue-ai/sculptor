# `sculptor` glossary

- `Task`: the primary unit of work in `sculptor` -- something the user wants done.
  The code that runs on the server is located in the `tasks` module,
  and is dispatched into via the `TaskInput` type of the `input_data` field.
  Typically, that code will create an `Environment` and then start an `Agent` in that environment.
- `Agent`: a process that implements the  `Agent` interface and observes an agent process, emitting `Message`s
  when new events are detected, and handling `Message`s from the user.
  `Agent`s are launched by running a `Task` with `CodingAgentTaskInputs`
- `Environment`: a running container, sandbox, or similar. Enables running processes (see the `Process` class.)
- `Image`: a collection of container layers. A docker image, modal sandbox, or the like. Used to launch an `Environment`.
- `Volume`: a remotely accessible filesystem that can be mounted into an `Environment`, and which persists across `Environment` restarts.
