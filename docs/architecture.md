# Overview

The purpose of `sculptor` is to help users get things done with AI agents.

Specifically, this means allowing users to create and manage tasks (`UserTask`s),
which are then worked on by AI agents (`Agents`) in environments (`Environments`).

For an end-to-end example of the request flow, see the [request flow diagram](diagrams/request_flow.md).

# Components

In order to accomplish `UserTask`s, `sculptor` is implemented as a simple web app.

`sculptor` is divided into three main components:
1. the backend (written in `python` and using `FastAPI`,)
1. the frontend (written in `TypeScript` and using `react`) and
1. the command-line interface (CLI) (also written in `python`.)

The backend handles the core logic of launching AI agents (`Agents`) in (generally sandboxed) environments,
as well as managing those agents and environments.
It also handles the associated data storage, event handling, and communication with the frontend.

The frontend provides a simple and extensible user interface
for interacting with the backend in order to create and manage tasks, agents, and environments.
It is designed to be easily accessible via browsers (even on mobile devices.)

The CLI provides a simple way to interact with the backend from the command line.

## Backend

The backend is architected as a standard web application,
with stateless handling of requests, a database for persistent storage, and a set of background workers for long-running tasks.

It is designed to be run both locally (e.g., under the full control of an individual user),
and remotely (e.g., in a cloud environment, where multiple users can use shared infrastructure.)

Currently, only the "local" mode is implemented.

The database currently supported is SQLite (though support is planned for PostgreSQL.)
Database models are defined using `pydantic` and `SQLAlchemy`.
Migrations are handled using `alembic`.

Tasks are simply `python` classes that implement the `WorkTask` interface.
They are run via the `task_service`, which is a simple in-process task runner.

## Frontend

Data types are defined using `pydantic`.
From these definitions, `TypeScript` types are generated via OpenAPI schemas.

## CLI

The CLI is a simple `python` script that uses the `Typer` library to provide a command-line interface.

Only a single command is currently implemented: `sculptor launch`,
which creates a new task and launches an agent to work on it.

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

# Module Structure

The `sculptor` codebase is organized into several modules, each with a specific purpose.
See the [README.md](sculptor/README.md) in the source root for details.
