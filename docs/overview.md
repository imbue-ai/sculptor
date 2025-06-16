See the [glossary](glossary.md) for a definition of the key concepts used in Sculptor.

At the highest level, Sculptor is a web application that allows users to create and manage tasks.

Today, these tasks are focused on running AI coding agents in environments in order to do software development tasks.

Operationally, we assume that our `Task` objects *are* "tasks" in the same sense of a task running library like `celery`,
eg, that they are long-running processes that can be scheduled and run in the background,
and which should be idempotent and retryable.

In order to run our coding agents, we simply use a single canonical task, `run_agent_task_v1`,
which accepts `AgentTaskInputsV1` inputs and runs the configured `Agent` in the configured `Environment`.

To create a new `Task`, the user simply sends an appropriate POST `Request` to the `/api/v1/task` endpoint.
The `TaskService` notices the new task and runs it in the background (like any sensible task processing system.)

The user can stream updates to a single task via the `/api/v1/tasks/{task_id}/stream` endpoint,
or can stream updates to all tasks via the `/api/v1/tasks/stream` endpoint.

These updates are effectively a materialized view of the `Task` state
(see the classes in `derived.py`, eg, `CodingAgentTaskView`),
given in a convenient format for the frontend to consume.

Users interact with running `Agent`s / `Task`s by sending `Message`s to the appropriate HTTP endpoint.
`Message`s from the user are inserted into the `Database`, which is observed by the task runner
(ie, the running `run_agent_task_v1` task.)

Certain `Message`s also control the lifecycle of the `Task` itself,
(e.g., the `User` can send `StopAgentUserMessage` to stop the agent)
