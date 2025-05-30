# Open design questions required for remote servers

We don't need to figure these out yet, just flagging them so we can start thinking about them.

## How should secret management work?

For now this is fine (load from local), but how do we want this to work when users launch from the web?

I would *very much* like to *not* be storing their secrets, bc that is bad from a security perspective.

The "right" way (from a security perspective) is to think about totally ephemeral everything --
that doesn't seem short term feasible though.

You could have users inject secrets only at task launch time,
but that breaks mobile + web launching.

We *could* store the secrets...  but ideally we would not.

Ideally they would have them in vault or something?  and could provide a key to unlock them?

Want to know a bit more how to do this...

## How exactly should we onboard people on to creating their own images?

This is a fairly tricky thing to do.

We should probably let them start out without requiring anything, and smoothly on-ramp them to adding some list of commands to build the image.

We'll also probably want to OAuth with their repo, etc to pull in the code.

More thought is definitely needed here.

## How can we ensure that keystrokes into terminals are fast?

In particular, we'll want direct connections to the `Environment`s (if at all possible.)

## How exactly should message passing work for tasks?

Currently, we just save all of them in the database but that's very inefficient.

It's complicated to move away from that though, because it stops being transactional.

For example -- without messages being transactional, how would you ensure that the start message was sent to a task right after it wsa started?

That's not impossible to handle in the specific case (ex: save just that start message and ensure that it makes it into the task)
but the more general case is harder.

Perhaps we could have special transactional messages? Or perhaps we only need to handle start and stop?

## How should task processing be done?

The current transactional approach is great, but we'll probably have to be careful about the efficiency of the implementation.

Even with a LISTEN/NOTIFY approach in postgresql, we may need to do something a bit more efficient for remote servers.

One possibility is to think about serverless approaches (ex: modal Functions) instead of running our own.
