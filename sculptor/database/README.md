# sculptor database

This module is responsible for storing all permanent application data.
It currently supports sqlite and postgresql databases.

We store all of our data in a dual form -- as a log of immutable events (in `${table_name}`,)
and as a materialized view of the current state (in `${table_name}_latest`.)
For the implementation of that logic, see [automanaged.py](automanaged.py).

For the exact schema definitions, see the [tables.py](tables.py) file.
All table classes end with `Row`, and ultimately inherit from `DatabaseModel`.

Each table has an ID class that is specific to that table, and which inherits from `ObjectID`.

Note that there are [3 different ways of mapping inheritance in SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/inheritance.html):
- single table inheritance – several types of classes are represented by a single table;
- concrete table inheritance – each type of class is represented by independent tables;
- joined table inheritance – the class hierarchy is broken up among dependent tables. Each class represented by its own table that only includes those attributes local to that class.
Plus one other alternative:
- dispatched json column data -- where each class is represented by a single table, but the data that changes is stored in a JSON column.

All of them have trade-offs, and the approach we use is case-specific:
- For `ExecutorVolumeRow` and `ExecutorImageRow` we use the concrete table inheritance,
  since the data is entirely different for each provider.
- For `Task` and `SavedAgentMessage`,
  we use the dispatched json approach since it doesn't really make sense to migrate the data --
  it will eventualy be completely agent-dependent anyway,
  and we'll want to think about how to gracefully deal with outdated data.
