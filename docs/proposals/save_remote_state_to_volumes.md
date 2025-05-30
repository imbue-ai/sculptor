# Better persist remote agent state

We could fairly easily put the outputs from an onto a persistent `Volume`.

That way if the remote agent is restarted it can pick up where it left off.
It would make it easier to recover crash logs as well.
Finally, it might provide a nice space for fundamentally storing that data (rather than in the database).
