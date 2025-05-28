small note -- there are actually a few kinds of time constraints
    "CPU time" -- how long it takes where it is actually running
        useful for preventing things from running for too long
    "wall time" -- how long it takes in the real world
        useful for ensuring that things finish in a timely manner
    "deadline" -- when the task *must* be done by
        useful for ensuring that something is done "in time"
        note that with agents, unlike with older style tools, this makes sense, but comes with trade-offs -- it can get much more complex and expensive to attempt to meet a deadline
    generally the first 2 should be set to reasonable limits by default, and the 3rd should be unset

there are lots of other things to limit too:
- network access
- secrets
- memory, CPU, disk, etc
- information access (eg, what files are available, what environment variables are set, etc)
- notifications / who you can contact and how you can contact them
