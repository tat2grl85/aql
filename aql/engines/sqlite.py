# Copyright 2019 John Reese
# Licensed under the MIT license

from typing import Any, List, Optional, TypeVar

from ..column import NO_DEFAULT, Primary, Unique
from ..errors import BuildError
from ..query import PreparedQuery, Query
from .base import Connection, Cursor, MissingConnector
from .sql import SqlEngine

try:
    import aiosqlite
except ModuleNotFoundError as e:  # pragma:nocover
    aiosqlite = MissingConnector(e)

T = TypeVar("T")


class SqliteEngine(SqlEngine, name="sqlite"):
    def create(self, query: Query[T]) -> PreparedQuery[T]:
        column_defs: List[str] = []
        column_types = query.table._column_types
        for column in query.table._columns:
            ctype = column_types.get(column, None)
            if not ctype:
                raise BuildError(f"No column type found for {column.name}")
            if ctype.root not in self.TYPES:
                raise BuildError(f"Unsupported column type {ctype.root}")
            parts = [f"`{column.name}`", self.TYPES[ctype.root]]

            if ctype.constraint == Primary:
                parts.append("PRIMARY KEY")
            elif ctype.constraint == Unique:
                parts.append("UNIQUE")
            if ctype.autoincrement:
                parts.append("AUTOINCREMENT")

            if not ctype.nullable:
                parts.append("NOT NULL")
            if column.default is not NO_DEFAULT:
                parts.extend(["DEFAULT", repr(column.default)])

            column_defs.append(" ".join(parts))

        for con in query.table._indexes:
            if isinstance(con, Primary):
                parts = ["PRIMARY KEY"]
            elif isinstance(con, Unique):
                parts = ["UNIQUE"]
            else:
                continue  # pragma:nocover
            columns = ", ".join(f"`{c}`" for c in con._columns)
            parts.append(f"({columns})")

            column_defs.append(" ".join(parts))

        ine = "IF NOT EXISTS " if query._if_not_exists else ""
        sql = f"CREATE TABLE {ine}`{query.table._name}` ({', '.join(column_defs)})"
        parameters: List[Any] = []
        return PreparedQuery(query.table, sql, parameters)


class SqliteCursor(Cursor):
    def __init__(self, conn: Connection, cursor: Optional["aiosqlite.Cursor"]):
        super().__init__(conn)
        self._cursor = cursor

    def __getattr__(self, key):
        return getattr(self._cursor, key)


class SqliteConnection(Connection, name="sqlite", engine=SqlEngine):
    async def connect(self) -> None:
        """Initiate the connection, and close when exited."""
        self._conn = await aiosqlite.connect(self.location, *self._args, **self._kwargs)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def query(self, query: Query[T]) -> Cursor:
        prepared = self.engine.prepare(query)
        cursor = await self._conn.execute(prepared.sql, prepared.parameters)
        return SqliteCursor(self, cursor)
