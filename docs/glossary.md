# `sculptor` glossary

- `Task`: the primary unit of work in `sculptor` --
  something the user wants done and/or a computational task (in the sense of a task running library like `celery`.)
  Note that, at least right now, these two concepts are intentionally conflated.
  The code that runs the task on the server is located in the `tasks` module,
  and is dispatched into via the `TaskInput` type of the `input_data` field.
  Typically, that code will create an `Environment` and then start an `Agent` in that environment.
- `Agent`: a process that implements the  `Agent` interface and observes an agent process, emitting `Message`s
  when new events are detected, and handling `Message`s from the user.
  `Agent`s are currently launched by running a `Task` with `CodingAgentTaskInputs`
- `Environment`: a running container, sandbox, or similar. Enables running `Process`
- `Process`: a running process in an `Environment`.  It has the same semantics as a posix process, but with a restricted interface.
- `Image`: a collection of container layers. A docker image, modal sandbox, or the like. Used to launch an `Environment`.
- `Volume`: a remotely accessible filesystem that can be mounted into an `Environment`, and which persists across `Environment` restarts.
- `Message`: messages are either sent by the user, the `Agent`, or the task runner itself.
  All communication between the user and the `Agent` is done via `Message`s.
- `Request`: a request is any HTTP request made by the user to the `sculptor` backend.
  Requests are handled by the `FastAPI` `Application` by using various `services` to read and/or write the application state.
  The user only interacts with the `sculptor` application via `Request`s, and by mutating the state of their filesystem.
- `Service`: a service is a class that encapsulates some of the `Application` state and provides methods to read and/or write that state.
  All access to the state is done via services.
- `Application`: the `sculptor` application, ie, the running `python` process that handles requests and runs tasks.
- `Database`: the persistent storage for the `sculptor` application. All persistent data is stored in the database.
- `Transaction`: we assume fully ACID-compliant transactions.
  All changes to the database are done in transactions, which means that `Request`s must deal with conflicts and retries.
- `User`: a (human) user of the `sculptor` application.
  Users are identified by a unique ID, and may be associated with multiple `Organization`s.
  Note that, while `sculptor` is designed to be multi-user, it is currently only used by a single user in a standalone desktop mode.
- `Organization`: a group of users.  `Project`s are associated with `Organization`s
  (and thus, indirectly, with `User`s.)
- `Project`: primarily a reference to the URLs (eg, git repositories, folders, etc) of the code being worked on.
