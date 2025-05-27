# Currently open design questions

## Should we use threads or processes for the task_service?

I wrote the first implementation using threads, but it's just kind of a bad idea --
it makes it really hard to cleanly shut down (unless you want to carefully spread a bunch of shutdown flag checking through basically everything, which I do not.)

I don't see a particularly compelling reason not to just use processes, so I think I'm going to re-write it to do that instead.

This has the additional benefit of making it much faster to shut down.

## Where, exactly, does the tmux scrollback buffer get syned to *on the server*?

Right now, we can probably sync the *logs* into the database and the *git branch* into the local repo,
but it's less clear where to put the tmux scrollback buffer (and raw stdout, stderr, etc.).

We could sync them to a file? Or make a special table in the database that contains them?
Logically it's very similar to the StreamingContainer's that we had before
(in that we don't want to continually make new records for each update)

## How, precisely, should the default claude agents know when they are blocked?

This is potentially a bit tricky, especially with the text-based one.

It *seems* like it should be possible to understand when there are any outstanding LLM or tool calls?
For example, [this project](https://github.com/1rgs/claude-code-proxy) wraps the claude LLM calls (in order to proxy them),
so that should be sufficient for us.

## How does streaming work from the inner coding agents?

In particular, it is a little bit tricky because the SDK interface seems to only provide complete responses,
so if we wanted to stream in the HTML version, we would probably need to intercept the LLM calls and stream them ourselves.

See the above link for an example of how to do this.

## What level does this tmux and ttyd hackery live on?

We start claude in tmux, and that's sort of baked into some of the logic.
We are also starting ttyd so that we can connect.
But this is clearly a bit of a special case of something more general.

At what level does this logic live? Should `Agent`s be tmux-aware, or should this be an implementation detail of some `Agent` implementations?

My current leading idea is that we should move this into *our* code that is called within the `Environment`, eg, the code that calls into the `Agent`.
Before calling in, we can set up tmux, start whatever process needs to be started in that tmux session, etc.

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

## What is the exact onboarding / startup sequence for the user?

It seems like:
- Run the command via uvx in your current repo, and that shows up as a project in the UI.
- Complain at you if you don't have docker installed (but possibly allow you to start in an unsafe way anyway?)
- Is there any way to add a project without running the command from that folder? Seems like we can start with "no"?
