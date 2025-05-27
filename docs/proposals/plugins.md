# Plugins

The `sculptor` codebase is designed to be extensible via plugins.

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

plugins for now then:
    make sensible interfaces, even if security isn't quite right
    make "events" so that we can define triggers
    there can be "backend" and "frontend" plugins already... kinda like middleware or whatever
    make as much of our own functionality this way as we can...
```
