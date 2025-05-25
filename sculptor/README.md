# Module layout

The `sculptor` codebase is organized into several modules, each with a specific purpose.

The modules are "layered" -- that is, each module may only depend on modules that are "lower" in the hierarchy.

From the top level down, the modules are:

- `testing`: test-related code, including fixtures, helpers and utilities for writing and running tests.
- `scripts`: scripts for running various tasks, such as deployment, creating tokens or generating TypeScript types from OpenAPI schemas.
- `plugins`: contains the default plugins for the application (since even some of the basic functionality is implemented as plugins.)
- `cli`: the command-line interface (CLI) for interacting with the application, allowing users to launch tasks and agents.
- `web`: the web interface for the application, including the frontend and backend components.
- `tasks`: the tasks that can be run by the application, which implement the `WorkTask` interface.
- `services`: the services that provide the core functionality of the application, such as task management and interacting with the database.  Each service has a canonical structure:
  - `*/api.py`: the API definitions for the service.
  - `*/data_types.py`: the data types defined by the service.
- `database`: the database-related code, including models and migrations.
- `core`: the core logic of the application, including data types, utilities, and common functionality.
- `config`: the configuration for the application, including settings and environment variables.
- `utils`: generic utility functions and classes that are used throughout the application.
- `version.py`: the version information of the application.

All front-end code is contained in `web/frontend` (see the `web/frontend/README.md` for more details.)

The top-level `tests` folder is *not* a module.
It contains the "integration" and "acceptance" tests for the application
(unit tests are located in the same folder as the code they test, and by convention are named the same as the file under test but with a `_test.py` suffix.)
