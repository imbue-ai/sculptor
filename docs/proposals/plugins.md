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
