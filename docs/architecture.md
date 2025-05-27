# Overview

The purpose of `sculptor` is to help users get things done with AI agents.

Specifically, this means allowing users to create and manage tasks (`UserTask`s),
on which we run `Agent`s in sandboxed environments (created via `Executor`s).

# High level flow

Below is an extremely high level overview of how `sculptor` works:

![image](https://i.postimg.cc/1XGR8HWN/image.png)
Generated from [diagrams/high_level_flow.md](diagrams/high_level_flow.md).

Breaking that down slightly more, here's a simplified diagram of the different parts of the system and how they interact:

![image](https://i.postimg.cc/5yYvTZ2W/image.png)
Generated from [diagrams/high_level_components.md](diagrams/high_level_components.md).

For a detailed end-to-end example of the request flow, see the [request flow diagram](diagrams/request_flow.md),
which is contained in [this eraser link](https://app.eraser.io/workspace/QJkmIoqQ9K2qjLBZIXbo)

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

Tasks are simply `python` classes that implement the `Task` interface.
They are run via the `task_service`, which is a simple in-process task runner.

## Frontend

Data types are defined using `pydantic`.
From these definitions, `TypeScript` types are generated via OpenAPI schemas.

## CLI

The CLI is a simple `python` script that uses the `Typer` library to provide a command-line interface.

Only a single command is currently implemented: `sculptor launch`,
which creates a new task and launches an agent to work on it.

# Module Structure

The `sculptor` codebase is organized into several modules, each with a specific purpose.
See the [README.md](sculptor/README.md) in the source root for details.
