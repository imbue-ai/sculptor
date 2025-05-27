# `sculptor` glossary

- `UserTask`: a user goal. Something the user wants to do. This is the primary unit of work in `sculptor`.
- `ServerTask`: the code that runs *on our server* in order to perform a `UserTask`.
  The code is dispatched into via the `ServerTaskInput` type in the `tasks` module.
- `Agent`: a process that implemented `AgentInterface` and which observes an agent process, emitting `AgentMessage`s
  when new events are detected, and handling `AgentMessage`s from the user.
  `Agent`s are launched by running a `ServerTask` with `CodingAgentServerTaskInputs`
- `Image`: a collection of container layers. A docker image, modal sandbox, or the like.
- `Volume`: a remotely accessible filesystem that can be mounted into a container, and which persists across container restarts.
- `Executor`: a running container, sandbox, or similar. Enables running processes (see the `CommandProcess` class.)
