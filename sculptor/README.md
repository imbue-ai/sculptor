# Module layout

The `sculptor` codebase is organized into several modules, each with a specific purpose.

The modules are "layered" -- that is, each module may only depend on modules that are "lower" in the hierarchy.

From the top level down, the modules are:

- `testing`: test-related code, including fixtures, helpers and utilities for writing and running tests.
- `scripts`: scripts for running various tasks, such as deployment, creating tokens or generating TypeScript types from OpenAPI schemas.
- `cli`: the command-line interface (CLI) for interacting with the application, allowing users to launch tasks and agents.
- `web`: the web interface for the application, including the frontend and backend components.
- `agents`: contains the default `Agent` implementations.
- `tasks`: contains the code for handling `Task`s.  This is done by dispatching on the `TaskInputs` type.
- `services`: the services that provide the core functionality of the application, such as task management and interacting with the database.
  Each service has a canonical structure:
  See the [`./services/README.md`](./services/README.md) for more details on each service.
  - `*/api.py`: the API definitions for the service.
  - `*/data_types.py`: the data types defined by the service.
- `database`: the database-related code, including all models and migrations. Most data-related classes live here.
- `interfaces`: the interfaces that define externally facing components of the application (ex: the `Agent` class.)
- `config`: the configuration for the application, including settings and environment variables.
- `utils`: generic utility functions and classes that are used throughout the application.
- `primitives`: the most basic types -- ids, enums, and other foundational data types.
- `version.py`: the version information of the application.

All front-end code is contained in `web/frontend` (see the `web/frontend/README.md` for more details.)

The top-level `tests` folder is *not* a module.
It contains the "integration" and "acceptance" tests for the application
(unit tests are located in the same folder as the code they test, and by convention are named the same as the file under test but with a `_test.py` suffix.)
