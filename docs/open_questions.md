# Currently open design questions

## Should there even be a database for the environment_service?

The only thing that REALLY needs to be saved is the images, and that's really just a caching thing.

For now, I think we can just ignore it and leave it as an implementation detail of the `EnvironmentService`.

Note that this is possible because the actual `Image` and `Volume` data is just serialized as JSON in the current_state of the `Task`.

## Should notifications be done in the same stream as the task events? Or in a separate stream?

See server.py

## How should we handle upgrades while tasks are in progress?

Currently, the `tasks` module is designed to make it possible to handle upgrades by versioning the task input types.
In this way, tasks could be resumed even if they were using an older set of inputs than the latest code.

This is more complex than I would like, but it doesn't matter that much -- for now we'll just be restarting tasks when the code changes anyway.
