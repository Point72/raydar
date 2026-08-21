"""Serializable batches of table operations.

The tracker actor and the dashboard may live in different processes, so table
creates, updates and clears are expressed as plain data rather than as calls
against a table handle. This module deliberately imports nothing heavy: it is
loaded inside cluster actors that never render a dashboard.
"""

from collections import deque

__all__ = ("OpBuffer",)


class OpBuffer:
    """Accumulates table operations until a consumer drains them.

    Used when the dashboard runs outside the cluster and pulls over Ray's own
    connection. ``schemas`` are replayed on every drain so a dashboard that
    starts late still learns about tables created before it connected.
    """

    def __init__(self, max_rows_per_table: int = 100_000):
        self._max_rows_per_table = max_rows_per_table
        self._schemas: dict[str, dict] = {}
        self._updates: dict[str, deque] = {}
        self._cleared: list[str] = []

    def new_table(self, tablename: str, schema: dict) -> None:
        self._schemas.setdefault(tablename, schema)

    def update(self, tablename: str, data) -> None:
        if isinstance(data, dict):
            data = [data]
        if not data:
            return
        rows = self._updates.get(tablename)
        if rows is None:
            rows = self._updates[tablename] = deque(maxlen=self._max_rows_per_table)
        rows.extend(data)

    def clear(self, tablename: str) -> None:
        self._updates.pop(tablename, None)
        if tablename not in self._cleared:
            self._cleared.append(tablename)

    def extend(self, batch: dict) -> None:
        """Absorb a batch in the same shape :meth:`drain` produces."""
        for tablename, schema in (batch.get("schemas") or {}).items():
            self.new_table(tablename, schema)
        for tablename in batch.get("cleared") or ():
            self.clear(tablename)
        for tablename, rows in (batch.get("updates") or {}).items():
            self.update(tablename, rows)

    def drain(self) -> dict:
        """Return the operations buffered since the last call and reset them."""
        batch = {
            "schemas": dict(self._schemas),
            "updates": {name: list(rows) for name, rows in self._updates.items() if rows},
            "cleared": list(self._cleared),
        }
        self._updates.clear()
        self._cleared.clear()
        return batch
