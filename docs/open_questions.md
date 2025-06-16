# Currently open design questions

## SHould the Message's have a created_at field?

You probably want to know *when* something happened.

However, putting the created_at in the Message is not great -- there is fundamentally clock skew,
and then people might think it was reasonable to sort by that field, which is not a good idea.

Right now, the Message's are properly serialized by virtue of being saved to the database,

Perhaps the field ought to be there, but be simply be given a name like `approximate_creation_time`.

I'll do that for now.

## Should the Message's be saved to the database or not?

**Tentative answer**: Yes. This will eventually be a performance problem, but for now it is probably fine,
and it's just much easier to reason about behavior when it is transactional.
Note that they will NOT require any migrations -- they're basically just saved as JSON rows, we're free to evolve the messages as needed.
I think I'll just make the data go through the `task_service` and then save it to the database as an implementation detail.

## Should we use threads or processes for the task_service?

I wrote the first implementation using threads, but it's just kind of a bad idea --
it makes it really hard to cleanly shut down (unless you want to carefully spread a bunch of shutdown flag checking through basically everything, which I do not.)

I don't see a particularly compelling reason not to just use processes, so I think I'm going to re-write it to do that instead.

This has the additional benefit of making it much faster to shut down.

**Tentative answer**: move to something that uses an Executor so that we can swap between `ProcessPoolExecutor` and `ThreadPoolExecutor` as needed
(though we will only use `ThreadPoolExecutor` for testing, and can set the threads to `daemon=True`.)

## How, precisely, should the default claude agents know when they are blocked?

This is potentially a bit tricky, especially with the text-based one.

It *seems* like it should be possible to understand when there are any outstanding LLM or tool calls?
For example, [this project](https://github.com/1rgs/claude-code-proxy) wraps the claude LLM calls (in order to proxy them),
so that should be sufficient for us.

**Tentative answer**: leaving this up to Guinness as he implements it.

## How does streaming work from the inner agents?

In particular, it is a little bit tricky because the SDK interface seems to only provide complete responses,
so if we wanted to stream in the HTML version, we would probably need to intercept the LLM calls and stream them ourselves.

See the above link for an example of how to do this interception.

**Tentative answer**: we can make a separate type of "streamed chunk" message that is meant to be aggregated by clients.
The full message WILL eventually be sent, but for streamed responses, we can just duplicate the data, that's fine -- it's at most a factor of 2x.

## What level does this tmux and ttyd hackery live on?

We start claude in tmux, and that's sort of baked into some of the logic.
We are also starting ttyd so that we can connect.
But this is clearly a bit of a special case of something more general.

At what level does this logic live? Should `Agent`s be tmux-aware, or should this be an implementation detail of some `Agent` implementations?

My current leading idea is that we should move this into *our* code that is called within the `Environment`, eg, the code that calls into the `Agent`.
Before calling in, we can set up tmux, start whatever process needs to be started in that tmux session, etc.

**Tentative answer**: we decided to move this into the actual "Agent"s themselves, ie, the code that is run in the `Environment`.
The outer process can be informed about these details by sending special `Message`s back.

## Where, exactly, does the tmux scrollback buffer get syned to *on the server*?

Right now, we can probably sync the *logs* into the database and the *git branch* into the local repo,
but it's less clear where to put the tmux scrollback buffer (and raw stdout, stderr, etc.).

We could sync them to a file? Or make a special table in the database that contains them?
Logically it's very similar to the StreamingContainer's that we had before
(in that we don't want to continually make new records for each update)

**Tentative answer**: like the above, we can have special `Message`s that tell the runner where to find the scrollback buffer.
Then they can be considered an "artifact" from the agent (with a file:/// url), and the syncer can just keep that file updated.

## Should there even be a database for the environment_service?

The only thing that REALLY needs to be saved is the images, and that's really just a caching thing.

For now, I think we can just ignore it and leave it as an implementation detail of the `EnvironmentService`.

Note that this is possible because the actual `Image` and `Volume` data is just serialized as JSON in the current_state of the `Task`.

**Tentative answer**: not needed for V1, can come back later.

## Should notifications be done in the same stream as the task events? Or in a separate stream?

See server.py

**Tentative answer**: we should go with a single stream for now (unless bryden says otherwise)

## How should we handle upgrades while tasks are in progress?

Currently, the `tasks` module is designed to make it possible to handle upgrades by versioning the task input types.
In this way, tasks could be resumed even if they were using an older set of inputs than the latest code.

This is more complex than I would like, but it doesn't matter that much -- for now we'll just be restarting tasks when the code changes anyway.

**Tentative answer**: *agents* should be commands that are fully versioned, while *tasks* should be versioned by their input data structure
(which will generally be backwards compatible, and when not, we can increment the version number in the data type so that migrations will work out.)

## What is the exact onboarding / startup sequence for the user?

It seems like:
1. Run the command via uvx in your current repo, and that shows up as a project in the UI.
2. Complain at you if you don't have docker installed (but possibly allow you to start in an unsafe way anyway?)
3. Is there any way to add a project without running the command from that folder? Seems like we can start with "no"?

**Tentative answers**: 1. yes, 2. complain + allow local with a big warning, 3. no.
