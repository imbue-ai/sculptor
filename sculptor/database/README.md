# sculptor database

This module is responsible for storing all permanent application data.
It currently supports sqlite and postgresql databases.

We store all of our data in a dual form -- as a log of immutable events (in `${table_name}`,)
and as a materialized view of the current state (in `${table_name}_latest`.)
For the implementation of that logic, see [automanaged.py](automanaged.py).

For the exact schema definitions, see the [tables.py](tables.py) file.
All table classes end with `Row`, and ultimately inherit from `DatabaseRow`.

Each table has an ID class that is specific to that table, and which inherits from `ObjectID`.
