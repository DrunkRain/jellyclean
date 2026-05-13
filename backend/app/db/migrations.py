"""Lightweight schema migration for SQLite.

`Base.metadata.create_all` only creates MISSING tables — it does NOT add new
columns to existing ones. We add them ourselves via `ALTER TABLE ADD COLUMN`,
deriving the SQL DEFAULT clause from the SQLAlchemy column's Python default so
NOT NULL columns can be added to non-empty tables.

Limitations (intentional, sufficient for this project's scale):
  - Only handles ADD COLUMN. No DROP, no rename, no constraint changes.
  - Callable defaults (e.g. `_utcnow`) cannot be expressed in SQL, so columns
    using them must either be nullable or be on a new table. Avoid for migrations.
  - If we ever outgrow this, switch to Alembic.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Column, inspect
from sqlalchemy.engine import Connection

from app.db.base import Base

log = logging.getLogger("jellyclean.migrations")


def _sql_default_clause(col: Column[Any]) -> str:
    """Translate a column's Python default into a SQL DEFAULT clause, when possible."""
    if col.default is None:
        return ""
    arg = getattr(col.default, "arg", None)
    if arg is None or callable(arg):
        return ""  # can't translate
    if isinstance(arg, bool):
        return f" DEFAULT {1 if arg else 0}"
    if isinstance(arg, (int, float)):
        return f" DEFAULT {arg}"
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def _migrate_sync(sync_conn: Connection) -> None:
    inspector = inspect(sync_conn)

    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            # Table will be created by create_all — nothing to migrate.
            continue

        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}

        for col in table.columns:
            if col.name in existing_cols:
                continue

            col_type = col.type.compile(dialect=sync_conn.dialect)
            default_sql = _sql_default_clause(col)
            # SQLite refuses NOT NULL on ADD COLUMN unless a DEFAULT is provided.
            # If we have no default, downgrade to nullable rather than crash —
            # better to keep the app booting and let the user supply values later.
            if not col.nullable and not default_sql:
                log.warning(
                    "Column %s.%s is NOT NULL without a translatable default; "
                    "adding as NULLABLE (manual fixup may be needed).",
                    table.name, col.name,
                )
                nullable_sql = ""
            else:
                nullable_sql = "" if col.nullable else " NOT NULL"

            sql = (
                f"ALTER TABLE {table.name} "
                f"ADD COLUMN {col.name} {col_type}{default_sql}{nullable_sql}"
            )
            log.warning("Schema migration: %s", sql)
            sync_conn.exec_driver_sql(sql)


async def migrate_schema(engine) -> None:
    """Run lightweight schema migrations against an async engine."""
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_sync)
