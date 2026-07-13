from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def get_conn() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(settings.db_dsn, row_factory=dict_row, autocommit=False) as conn:
        yield conn
