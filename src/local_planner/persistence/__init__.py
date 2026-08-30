"""SQLite adapter. Domain never connects or BEGIN/COMMIT."""

from local_planner.persistence.connection import open_connection
from local_planner.persistence.store import SqliteUnitOfWork

__all__ = ["SqliteUnitOfWork", "open_connection"]
