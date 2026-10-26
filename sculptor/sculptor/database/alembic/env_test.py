"""Running the migrations against the database named by the Alembic CLI's `-x dburl=` argument."""

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import inspect

from sculptor.database.alembic.utils import get_alembic_script_location


def test_a_percent_encoded_dburl_argument_migrates_the_database_it_names(tmp_path: Path) -> None:
    (tmp_path / "jöe").mkdir()
    config = Config(cmd_opts=Namespace(x=[f"dburl=sqlite:///{tmp_path}/j%C3%B6e/database.db"]))
    config.set_main_option("script_location", get_alembic_script_location())

    command.upgrade(config, "head")

    migrated = create_engine(f"sqlite:///{tmp_path / 'jöe' / 'database.db'}")
    assert "alembic_version" in inspect(migrated).get_table_names()
