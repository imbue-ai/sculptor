# Currently open design questions

there's a weird split between user task events and agent messages...
    very similar, one is just stored in the DB...
    and one doesn't have an ID...
    should really probably fix


should there even be a database for the executor service...
    the only thing that REALLY needs to be saved is the images
    and that's really just a caching thing


## Should notifications be done in the same stream as the task events? Or in a separate stream?

See server.py

## How should we handle upgrades while tasks are in progress?

Currently, the `tasks` module is designed to make it possible to handle upgrades by versioning the task input types.
In this way, tasks could be resumed even if they were using an older set of inputs than the latest code.

This is more complex than I would like, but it doesn't matter that much -- for now we'll just be restarting tasks when the code changes anyway.
