# Service hierarchy

The `sculptor` services, like the top level modules, are "layered" --
that is, each service may only depend on services that are "lower" in the hierarchy.

From the top level down, the services are:

- `task_service`: manages tasks, including task execution and scheduling.
- `executor_service`: manages environments in which tasks and agents run.
- `git_repo_service`: manages Git repositories, including cloning and pushing changes.
- `data_model_service`: manages data models, including loading and saving data to and from the database.
- `agent_config_service`: manages agent configurations, including loading and saving configurations.
