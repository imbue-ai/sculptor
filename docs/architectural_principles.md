# `sculptor` architectural principles

There are a small number of principles and patterns that guide the architecture of the `sculptor` project.
These principles are not strict rules, but rather guidelines that help maintain a consistent and understandable codebase and approach to solving problems.

## Immutability

## Structured Concurrency

implicit in all of this -- the notion of "task groups" as a fundamental first class primitive so that you dont shoot your leg off
    the Modal.App primitive is amazing for making proper task groups...
    this MOSTLY gets tricky once things get remote OR if you were to shut down the server and want things to continue running (let's not do that)
    ok, so dealing with this when remote...
        we basically just need to ensure that our tasks themselves are modal.App style things
        or, any executor context needs to ENSURE that the container goes away
        sure, it could get hard killed
        that means that the actual execution services should be *primarily* responsible for this (like modal)
        can do similar things in the containers -- if no heartbeat, shut down, etc
        but you DO want a DUAL handshake here -- when resuming a task, if you see something around from before, you can try to use it I guess
        and periodically, we want to scan for places where this has gone horribly wrong (future)
