we want the user to be able to mix *their* tool invocations in with the *agents* tool invocations (eg, how does this work in this "interactive" mode...)
    worst case you can just make it a user message
    this is part of the Agent interface I guess, sure (invoke a tool manually, show me the output)

tools.toml is *for configuring our imbue MCP*
    we enable a sort of MCP supeset of behavior beyond other MCPs, eg, we can allow tools to see the entire history, fork, launch, etc
    it should not be referred to be the orchestrator at all!
    beyond potentially the manual tool invocations? but even there, it is just one of many
        perhaps there could be extra instrumentaion for those if we really wanted though, some sort of tool conventions if necessary
