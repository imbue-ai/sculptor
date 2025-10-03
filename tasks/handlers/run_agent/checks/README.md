# Checks

See original spec and slack discussion here for more detail and historical context: [https://imbue-ai.slack.com/archives/C091PTEBDMH/p1755111385073029](https://imbue-ai.slack.com/archives/C091PTEBDMH/p1755111385073029)
Note that it links to an even earlier doc about checks and suggestions in there as well!

See the [glossary](../../../../../docs/glossary.md) for definitions of terms used in this doc.

## User stories

As a user, I want to...
- know what to do next / be given some ideas about next steps to take
- know whether my tests still pass after the agent has made changes
- know what problems (if any) there are with code written by an agent
- distinguish between if existing tests broke vs. if new tests written by Claude are broken
- be able to configure when checks run, and provide dynamic rules (e.g. prompts) for when to run them

## Overview

The UI for this feature includes 2 artifact panels:
- `checksArtifactView`
- `newSuggestionsArtifactView`

It also contains a new inline chat row to display the status of checks in the `FIXME: PUT NAME HERE` component.

The information for these views is assembled on the frontend in `useTaskSSE`, where the data sent in via `TaskUpdate`s is aggregated on the front end.
This aggregation is perhaps needlessly efficient right now.
The information for those `TaskUpdate`s is assembled in `convert_agent_messages_to_task_update` by aggregating the various `Message`s sent by the agent and the task runner.

Thus, the fundamental source for all of this information is `Message`s that are sent by either the `CheckProcessController` or the `CheckProcess`s that it launches.

All check-related processing is handled by the `CheckProcessController`, which is launched by the `RunAgentTaskHandler`.

The `CheckProcessController` has only 4 public methods:
- `start`: a context manager that starts a thread for reading out the previous check and suggestion related information from the task filesystem (see `Data Layout` below for a description of how this data is laid out on disk.)
   Once these previous `Suggestion`s and `CheckProcess`es are read, `Message`s are emitted to inform the front end of the existing state.
- `on_persistent_user_message`: called when the user sends a `ChatInputUserMessage`.  All checks and suggestions are keyed off of these messages.
- `on_filesystem_change`: called when the filesystem changes, eg, when the agent has finished replying and the runner has taken a snapshot.
- `handle_message`: called when the runner receives a `Message`. This is used to handle messages from the user, eg, `StopCheckUserMessage` and `RestartCheckUserMessage` to stop and restart checks.

In response to the above events, the `CheckProcessController` may launch, stop, or restart `CheckProcess`es.
A `CheckProcess` is a subprocess that runs either within the `Environment` of the `Task` or in a specially isolated `Environment` that is spawned by the `CheckProcess` (future work -- no yet implemented, will be soon.)
The stdout of a `CheckProcess` is observed in order to parse any emitted `Suggestion`s.
Once observed, `Suggestion`s are both stored on the `Task` filesystem, and emitted as `NewSuggestionRunnerMessage`s in order to inform the user of new suggestions.
`Suggestion`s are also created if the `CheckProcess` exits with a non-zero exit code.

`CheckProcess`es run `Check`s, which are defined in the user's `.sculptor/checks.toml` file in their repo.
When no `Check`s are defined, a `Suggestion` is made to add some.
See [`check_loading.py`](./check_loading.py) for more information about the file format for `checks.toml`

There are default `Check`s as well ("system" checks) that sculptor can use to define hard-coded logic to make `Suggestion`s in certain situations (ex: if there are issues with configuration or the current system).

## Data layout

The `CheckRunOutputLocation` class (see [`output_location.py`](./output_location.py)) is the `python` class that defines how check-related data is laid out on disk.

The data is structured as follows:
```
f"{self.root_data_path}/{self.task_id}/checks/{self.user_message_id}/{self.check_name}/{self.run_id}"
```

This provides a bit of structure that makes it easier to see/debug what is going on.

The `/checks/` folder is in the path because we probably want to add `/artifacts/` there in the future,
for storing the current output artifacts from the agent (ex: the git diff, etc)

The root_data_path is just `AGENT_DATA_PATH` right now (`/agent/data`), but we can eventually read this from a `devcontainer.json` or other config if we want.

Note that all data is prefixed by `task_id` -- this is because we *share this volume across all tasks*.
This is done for efficiency -- without this, we would be snapshotting this entire set of data every time, and the outputs of commands that you run can grow extremely large (ex: each of our CI runs emits almost 100MB of logs alone.  If you included all video files, traces, etc, it would probably be bottlenecked on streaming the data over the network).

Because of this, we need to be careful to copy all of this state whenever we `fork` a task (see: `_restore_check_controller_state`).
Note that we've decided that a forked version of a task should only see the checks and suggestions data that was present at the time of the fork (it is not continually updated afterward, though technically it could be accessed if you knew the parent task id).

Within the `/checks/` folder, the next layer of structure is the `user_message_id`.
This is because we store the *current* checks into a file (`ALL_CHECKS_FILE_NAME`, currently `checks.json`) based on the state of the checks config file whenever it is reloaded.
Note that it is reloaded whenever the filesystem changes (and a `ChecksDefinedRunnerMessage` is emitted) so that the frontend can be aware of what checks are currently defined.

Finally, the data is further structured by `check_name` and `run_id`.
This is because we want to store the output of each individual run of a check separately both for debugging and for reloading when the task is restarted.
The data that is stored includes `stdout`, `stderr`, the exit code, the reason the `Check` finished, and any `Suggestion`s that were emitted.
See the `run` method of the `CheckProcess` class in [`check_process.py`](./check_process.py) for the exact data that is stored.

The current code gracefully handles cases where previously serialized `Check`s and `Suggestion`s are no longer deserializable.
One could imagine migrating this data, but it doesn't currently seem worth it, especially given how infrequently we expect users to view historical `Check`s.
