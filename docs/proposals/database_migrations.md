# Data migrations

## Assumptions

- We want to support locally running, isolated single-user servers as well as a centrally managed multi-user server.
- We want to support SQL schema migrations.
- We want to support data migrations, especially migrations of JSON blobs (e.g. in SavedAgentMessage).

## Considerations

- Atlas vs Alembic
    - Atlas:
        - is focused mostly on schema migrations and less on data migrations
        - requires installation of a separate non-python tool.
        - is opinionated and explicitly designed around migrating at deployment time (as opposed to at application startup time).
    - Alembic:
        - can capture both schema migrations and data migrations as the same kind of Python code
        - can ship migrations simply as a few additional Python modules alongside the app
        - is friendly towards us migrating at application startup in cases where it's justified (e.g. with the locally running single-user servers)

## Proposal

- Let's use Alembic for migrations.
- Track migrations "from scratch" as an ever growing set of python modules that implement the migration logic.
- In parallel to that, also keep track of the json schema of the latest version of the the nested pydantic models (the json blob(s) e.g. on SavedAgentMessage).
- In CI:
    - Have a test that runs the existing migrations from scratch on an in-memory database, compares the resulting schema with the schema from a freshly created DB and fails in case of differences.
    - Have another test that checks the latest json schemas against the actual pydantic models and fail in case of differences.
- Have a script for migration autogeneration.
    - Typically run by the developer facing failures from the previous step.
    - The script would do the following (if necessary):
        - Alembic's autogenerate functionality would be used to generate the SQL schema migration.
        - The frozen json schema would be updated.
        - An empty data migration for the json blobs would be created with `raise NotImplementedError()`.
            - It's up to the developer to implement it (or delete if not actually needed).
- Local servers:
    - Would attempt to run all (new) migrations at startup.
- (Future) Centrally managed server:
    - Runs migrations as part of the deployment process. Does not run migrations at startup.


## Risks

- Migrations will fail locally.
    - This is especially likely for the json-related data migrations because we won't be able to test them with all the various data that can exist in the wild.
    - Suggested mitigation: let's have a crude escape hatch for the local servers where we'd nuke the local DB when migrations fail.
- Migrations will be too slow.
    - This is mostly relevant for the data migrations.
    - Suggested mitigation (in the future): let's come up with a way of retiring old data.


## Open questions

- Do we actually need old messages?
- Do we need to support migrations when the app is running / tasks are in progress?
- Where and how should we indicate progress and status of locally running migrations, including nuking of the DB in case migrations fail?


## Alternatives

- We could keep throwing away old data instead of trying to keep it relevant via migrations.
    - However, even if we did that, we would probably reuse many of the above building blocks in order to detect breaking changes in the first place.
    - Which means that going with migrations for starters isn't that much of wasted effort even if we eventually end up throwing away old data instead.
