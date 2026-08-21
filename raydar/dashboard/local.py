"""Run the dashboard in the caller's process.

This is the mode that needs no inbound port on the Ray cluster. The web server
binds to the caller's machine and pulls table operations from the tracker actor
over the connection Ray already holds, so the browser only ever talks to
localhost and the cluster only ever accepts Ray traffic.
"""

import asyncio
import logging
import socket
import threading
from collections.abc import Callable

import uvicorn

from .dashboard import Dashboard

logger = logging.getLogger(__name__)

__all__ = ("LocalDashboard",)


class LocalDashboard:
    """A :class:`~raydar.dashboard.dashboard.Dashboard` served from a background thread.

    Args:
        drain: A callable returning the next batch of table operations, or None
            when there is nothing to apply. Called from a worker thread, so it
            may block.
        host: Interface to bind. Defaults to loopback.
        port: Port to bind, or 0 to let the OS pick a free one.
        poll_interval: Seconds between calls to ``drain``.
        **kwargs: Forwarded to :class:`~raydar.dashboard.dashboard.Dashboard`.
    """

    def __init__(
        self,
        drain: Callable[[], dict | None],
        host: str = "127.0.0.1",
        port: int = 0,
        poll_interval: float = 0.5,
        **kwargs,
    ):
        self._drain = drain
        self._host = host
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None

        if host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(f"raydar dashboard is bound to {host} and serves Ray task metadata without authentication")

        # Bind up front so `url` is accurate before the server thread starts.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket.listen(128)
        self.port = self._socket.getsockname()[1]

        self.dashboard = Dashboard(background=[self._poll], **kwargs)
        config = uvicorn.Config(self.dashboard.app, log_level="warning", lifespan="on")
        self._server = uvicorn.Server(config)
        # uvicorn installs signal handlers, which is only legal on the main thread.
        self._server.install_signal_handlers = lambda: None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}"

    async def _poll(self) -> None:
        while True:
            # Applying is inside the guard too: one bad row must not kill the loop
            # and leave the dashboard silently frozen.
            try:
                batch = await asyncio.to_thread(self._drain)
                if batch:
                    self.dashboard.apply(batch)
            except Exception:
                logger.exception("Failed to apply dashboard updates")
            await asyncio.sleep(self._poll_interval)

    def start(self) -> str:
        """Start serving in a daemon thread and return the dashboard URL."""
        if self._thread is not None and self._thread.is_alive():
            return self.url
        self._thread = threading.Thread(
            target=lambda: asyncio.run(self._server.serve(sockets=[self._socket])),
            name="raydar-dashboard",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"raydar dashboard serving at {self.url}")
        return self.url

    def stop(self) -> None:
        """Ask the server to exit and wait for the thread to finish. Idempotent."""
        self._server.should_exit = True
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                # Keep the reference so `start` cannot bind a second server to this socket.
                logger.warning("raydar dashboard thread did not stop within 5s")
                return
            self._thread = None
        self._socket.close()
