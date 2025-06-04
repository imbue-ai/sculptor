# Plugins

The `sculptor` codebase could be designed to be extensible via plugins.

The full interface is still in active development, but the intent is to support plugins of at least a few different types:
- "Agents" are effectively plugins that implement the `Agent` interface.
  They can be used to create new types of agents that can work on tasks.
- "Tools" are plugins that implement the `AgentTool` interface.
  They can be used to create new types of tools that agents can use to accomplish tasks.
- "Middleware" are plugins that implement the `Middleware` interface.
  They can be used to create new types of middlewares that can be used to modify requests and responses, or take actions based on events.
- "Interfaces" are plugins that implement the `InterfaceSurface` interface.
  They can be used to create new types of interfaces that can be used to interact with the backend.
  Unlike the other types of plugins, these plugins are written in `TypeScript` and are intended to be used in the frontend.

There are a lot of exciting possibilities here, but also some challenges:
- plugin ecosystems live or die by how they are curated and maintained.
  Just having a bunch of crap plugins is not a good experience for anyone.

There's something really interesting about plugins here though --
since our product is about writing code, it ought to be possible to enable people to generate their own plugins!
They could even do that *conditioned on existing plugins*, which might make it less of an issue if some plugin isn't perfect.

Other earlier raw thoughts

```
think about: plugin architecture
    I really think there's something super powerful here...
    there are only a few places where you can plug in:
        there are various "surfaces" for the UIs:
            task preview
            "perspective" on a single task (diff, nice log viewer, etc)
            task launching input area (that's something that's a little harder to make pluggable, we'll probably have to do that)
            this can be used to make, eg, an editor!  (though for that, you do need executor access, and likely want to get an exclusive lock, etc)
            then you can more easily see the result of tool calls, etc too ()
        then there are the programs that can be invoked:
            tools: called via MCP, eg, no extra context, and they are returned inline
            agents: forked from some context, eg, they inherit all of it, and show up as subtasks
        finally, there are "contexts" in which you can execute:
            the executors
            git repos
            data, etc
            permissions, etc
        there are also a class of plugins that observe logs of agents / tools, and then do something with those observations
            eg, intervene, cancel them, notify you, log them, etc
        main action button area (in the upper right)
            so that you can add things like merge, commit, push, local sync, etc
    and for ALL of them, we can enable you to easily make your own extensions!
        ex: wrap tools
        ex: simple agents
        ex: triggers
    as we are right now, we easily support plugins for:
        agents
            validate can be done without running untrusted code
            ahhh -- this is a good reason to treat them all as untrusted data and do the interface that way, not programmatically then... (or at least be careful about which parts go where)
        tools
            that's easy, just normal MCP things
        UI surfaces...
            this is harder to do in a way that is sandboxed...
            this is also considerably harder when we've got the event stream being processed on the back end
            I think I come back to this part later
        triggers
            also have to come back to this
    design: make sensible namespace spec for agent outputs and event types, document, etc for plugins, make extensible
        what if the agents had all possible outputs?  suggestions, code diffs, confidence about whether they had accomplished their goal, etc
        then there wouldn't need to be any separate notions for anything, really...
        would make the whole thing much much more flexible...
        and seems much more composible as well... could make a whole agentic coding framework out of this...
        esp if combined with the branches idea...

even sentry really seems like a plugin...
    oh neat -- and then sentry is just a "triggered event" that looks at the log and reports things when there are errors :)
    which is literally how we implemented it...
    and this can happen both inside and outside of your program...
        eg, you can almost trivially add sentry reporting to any of these tools

plugins for now then:
    make sensible interfaces, even if security isn't quite right
    make "events" so that we can define triggers
    there can be "backend" and "frontend" plugins already... kinda like middleware or whatever
    make as much of our own functionality this way as we can...

concrete plugin ideas:
get a summary of a PR at the end
local sync is just a plugin
    when you run the client locally, it connects to the server, and then you're able to sync to/from your local machine (potentially even automatically)
plugins make it really easy to wait for the right state, define triggers, etc
    there's something, in practice, about being able to wait for the right information to be available at some state
    ex: I want to understand current test coverage on the current diff, thus I want to wait until the tests are done running and aggregated
        then it's easy to express the "if the coverage is low, please write tests to test the basic functionality" trigger + program...
handle ambiguity: after a message is sent, run a checker to see if there was anything that could have been better specified
handle ambiguity: after a response is received, run a checker to see anything was assumed that was not in the original request
linear
what if we leaned into it?
    what if we made it easy to write tests
    or it auto wrote tests for you?
    and improved coverage
    and docs, linters, etc
    made sure that you had a design, and test plan, and that they all.worked together
    and helped suggest how to refactor
    or just stay with testing, checking that it is what you want
    finding those places where it is not...
we could send you suggestions async: email, slack, etc
personal search
    if we think about this almost as a way of organizing chats...
    then we care about being able to search over old chats
    constantly restarting them from a sensible state
    and thus pulling in personal info too!
    my whole personal info finder and query system goes here...
    but also, for knowledge work
    and it is local...
run locally
    obv our commands can run locally
    and we can upsell you on containers!
    and on sync offline execution
    makes setup so much easier...
auto summarize
    after commit
    as a way of making it fast and good to roll forward
    just a tool, like suggest
layout: chat plus tools, diff, log, terminal, editor?, subtasks?, suggestions?, (git) history
we could have a whole separate tab for always doing whatever you want in the agent container!
    ofc you could fuck it up, but that's still pretty cool
    in case it gets stuck, or you just want to see a diff, or whatever, it could be right there
summarize my previous work so far
this is something I should add to long term memory
make tests of new code without coverage (to demonstrate that they work)
make tests of new code (to identify and fix potential problems)
(literally whatever else we feel like invoking...)
```
