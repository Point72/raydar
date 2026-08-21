"""Perspective tables plus the spaday app that renders them.

A :class:`Dashboard` owns everything the browser talks to: the Perspective
server holding the tables, the transports session holding the UI state, and the
Starlette app that serves the page. It is deliberately free of any Ray
dependency so it can run in the caller's process, in a Ray Serve replica, or
standalone.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import perspective
import transports
from perspective.handlers.starlette import PerspectiveStarletteHandler
from spaday import Wire
from spaday.backends.starlette import serve as spaday_serve
from spaday_perspective import package as perspective_package
from spaday_webawesome import package as webawesome_package
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import __version__
from .page import STYLES, build_page
from .state import DashboardState, default_layout

__all__ = ("Dashboard", "TableHost")


class TableHost:
    """Owns a Perspective server and the tables served over its websocket."""

    def __init__(self, limit: int | None = None):
        self.server = perspective.Server()
        self._client = self.server.new_local_client()
        self._limit = limit
        self._schemas: dict[str, dict] = {}
        self._tables: dict[str, Any] = {}

    def names(self) -> list[str]:
        return list(self._schemas)

    def total_rows(self) -> int:
        """Rows currently held, which `limit` and `clear` both reduce."""
        return sum(table.size() for table in self._tables.values())

    def new_table(self, tablename: str, schema: dict) -> bool:
        """Create a table, returning whether it did not already exist."""
        if tablename in self._schemas:
            return False
        self._schemas[tablename] = schema
        kwargs = {"name": tablename}
        if self._limit is not None:
            kwargs["limit"] = self._limit
        self._tables[tablename] = self._client.table(schema, **kwargs)
        return True

    def update(self, tablename: str, data) -> None:
        if isinstance(data, dict):
            data = [data]
        if tablename not in self._tables:
            raise KeyError(f"No such table: {tablename}")
        self._tables[tablename].update(data)

    def clear(self, tablename: str) -> None:
        if tablename in self._tables:
            self._tables[tablename].clear()


class Dashboard:
    """The raydar UI: Perspective tables, UI state, and the Starlette app.

    Args:
        title: Page title and brand text.
        limit: Optional per-table row cap, applied to every table created.
        layout: A perspective-workspace layout to use instead of the generated
            one-tab-per-table default.
        background: Factories for coroutines to run for the lifetime of the app.
            Factories rather than coroutines so nothing is created for a
            dashboard that is never served.
    """

    def __init__(
        self,
        title: str = "raydar",
        limit: int | None = None,
        layout: dict | None = None,
        background: Sequence[Callable[[], Awaitable]] = (),
    ):
        self.tables = TableHost(limit=limit)
        self.state = DashboardState()
        self._layout_override = layout

        self._session = transports.Session()
        self._session.host(self.state)
        self._transport = transports.Server(self._session)

        @asynccontextmanager
        async def lifespan(_app):
            factories = (lambda: transports.autosync(self._transport), *background)
            tasks = [asyncio.ensure_future(factory()) for factory in factories]
            try:
                yield
            finally:
                for task in tasks:
                    task.cancel()

        self.app = spaday_serve(
            build_page(title, __version__),
            title=title,
            packages=[perspective_package, webawesome_package],
            # spaday infers "source" from a `js/` dir next to its package, which some
            # unrelated wheels create in site-packages. raydar always consumes the
            # packaged assets, so say so rather than rely on the heuristic.
            layout="installed",
            wire=[Wire("/ws", namespace="rd", flatten=False)],
            routes=[
                WebSocketRoute("/ws", transports.ws_endpoint(self._transport)),
                WebSocketRoute("/perspective", self._perspective_socket),
            ],
            lifespan=lifespan,
            store={"dark": False},
            head=STYLES,
        )

    async def _perspective_socket(self, websocket: WebSocket) -> None:
        try:
            await PerspectiveStarletteHandler(perspective_server=self.tables.server, websocket=websocket).run()
        except WebSocketDisconnect:
            pass

    def apply(self, batch: dict) -> None:
        """Apply a drained :class:`~raydar.ops.OpBuffer` batch to the tables."""
        changed = False
        for tablename, schema in (batch.get("schemas") or {}).items():
            changed |= self.tables.new_table(tablename, schema)
        for tablename in batch.get("cleared") or ():
            self.tables.clear(tablename)
            changed = True
        for tablename, rows in (batch.get("updates") or {}).items():
            if rows:
                self.tables.update(tablename, rows)
                changed = True
        # Schemas are replayed on every drain, so most batches are empty; only
        # touch the synced model when something actually moved.
        if changed:
            self._refresh_state()

    def _refresh_state(self) -> None:
        names = self.tables.names()
        if names != self.state.tables:
            self.state.tables = names
            self.state.layout = self._layout_override or default_layout(names)
        self.state.rows = f"{self.tables.total_rows():,}"
        self.state.status = "Live" if names else "Waiting for data"
        self.state.updated = datetime.now(tz=UTC).astimezone().strftime("%H:%M:%S")
