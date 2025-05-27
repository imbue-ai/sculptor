# Open design questions required for remote servers

We don't need to figure these out yet, just flagging them so we can start thinking about them.

## How exactly should we onboard people on to creating their own images?

This is a fairly tricky thing to do.

We should probably let them start out without requiring anything, and smoothly on-ramp them to adding some list of commands to build the image.

We'll also probably want to OAuth with their repo, etc to pull in the code.

More thought is definitely needed here.

## How can we ensure that keystrokes into terminals are fast?

In particular, we'll want direct connections to the `Environment`s (if at all possible.)

## How should task processing be done?

The current transactional approach is great, but we'll probably have to be careful about the efficiency of the implementation.

Even with a LISTEN/NOTIFY approach in postgresql, we may need to do something a bit more efficient for remote servers.

One possibility is to think about serverless approaches (ex: modal Functions) instead of running our own.
