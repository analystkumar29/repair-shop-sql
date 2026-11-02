"""Shared fixtures: generate the dataset once per test run and load it into an in-memory DuckDB."""

import pytest

import generate_data
import run_queries


@pytest.fixture(scope="session")
def tables():
    """Every table as a list of row dicts, straight from the generator (default seed)."""
    return generate_data.generate(generate_data.SEED)


@pytest.fixture(scope="session")
def data_dir(tables, tmp_path_factory):
    """The same tables written out as CSV files in a temporary folder."""
    folder = tmp_path_factory.mktemp("data")
    generate_data.write_csvs(tables, folder)
    return folder


@pytest.fixture(scope="session")
def db(data_dir):
    """An in-memory database built from schema.sql and those CSV files."""
    con = run_queries.build_database(db_path=None, data_dir=data_dir)
    yield con
    con.close()
