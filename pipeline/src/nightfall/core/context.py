"""As-of data access. Every read goes through here, so nothing can see the future.

A staged table declares which column says "when could we have known this row". ``Context``
adds ``<column> <= as_of`` to every read. Backtests replay many ``as_of`` values over one
connection; production uses ``as_of = now``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import duckdb

from nightfall.core.lake import Lake

# table -> (column, kind). kind: "date" compares to as_of.date(); "ts" compares to as_of.
ASOF_COLUMN: dict[str, tuple[str, str]] = {
    "eia_spot": ("available_on", "date"),
    "fx_usd_php": ("available_on", "date"),
    "pink_sheet": ("available_on", "date"),
    "price_weekly": ("available_on", "date"),
    "da_weekly_all": ("available_on", "date"),
    "port_daily": ("available_on", "date"),
    "chokepoint_daily": ("available_on", "date"),
    "storm_points": ("issued_at", "ts"),
    "storm_segments": ("issued_at", "ts"),
    "route_forecast": ("issued_at", "ts"),
    "ibtracs_points": ("time", "ts"),
    "news_items": ("first_seen", "ts"),
    "gdelt_articles": ("seen", "ts"),
    "aircraft_obs": ("observed_at", "ts"),
    "ais_positions": ("observed_at", "ts"),
    "ais_static": ("observed_at", "ts"),
}
UNVERSIONED = {"port_ref"}  # reference-like tables with no as-of column


@dataclass
class Context:
    con: duckdb.DuckDBPyConnection
    as_of: datetime

    @classmethod
    def from_lake(cls, lake: Lake, as_of: datetime) -> Context:
        return cls(lake.connect(), as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC))

    def at(self, as_of: datetime) -> Context:
        """Same data, different knowledge horizon (used by backtests)."""
        return Context(self.con, as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC))

    # -- reads -------------------------------------------------------------------------------
    def has(self, table: str) -> bool:
        row = self.con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [f"staging_{table}"],
        ).fetchone()
        return bool(row and row[0])

    def rows(
        self, table: str, where: str = "", params: list[Any] | None = None, order: str = ""
    ) -> list[dict]:
        if not self.has(table):
            return []
        clauses: list[str] = []
        args: list[Any] = []
        if table in ASOF_COLUMN:
            col, kind = ASOF_COLUMN[table]
            clauses.append(f"{col} <= ?")
            args.append(self.as_of.date() if kind == "date" else self.as_of)
        elif table not in UNVERSIONED:
            raise KeyError(f"table {table!r} has no as-of rule; add it to ASOF_COLUMN")
        if where:
            clauses.append(f"({where})")
            args.extend(params or [])
        sql = f'SELECT * FROM "staging_{table}"'
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if order:
            sql += f" ORDER BY {order}"
        cur = self.con.execute(sql, args)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def latest_issue(self, table: str) -> datetime | None:
        """Newest ``issued_at`` known at as_of, for forecast tables."""
        rows = self.rows(table, order="issued_at DESC")
        return rows[0]["issued_at"] if rows else None

    @property
    def today(self) -> date:
        return self.as_of.date()
