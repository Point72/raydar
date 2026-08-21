"""Serve the dashboard from inside the Ray cluster.

This mode requires an inbound port on the cluster, which is what
:mod:`raydar.dashboard.local` exists to avoid. It remains available for
clusters that already expose Ray Serve's HTTP ingress.
"""

from ray.serve import deployment, ingress

from .dashboard import Dashboard

__all__ = ("RaydarDeployment",)


@deployment(name="raydar_dashboard", num_replicas=1)
@ingress()
class RaydarDeployment:
    """A single replica owning the Perspective tables and the spaday app.

    The app is built by ``__serve_build_asgi_app__`` rather than handed to
    ``ingress``: it holds a Perspective server and a transports store, neither
    of which survives the pickling Ray Serve does to ship an app to a replica.
    """

    def __init__(self, title: str = "raydar", limit: int | None = None, layout: dict | None = None):
        self.dashboard = Dashboard(title=title, limit=limit, layout=layout)

    def __serve_build_asgi_app__(self):
        return self.dashboard.app

    async def apply(self, batch: dict) -> None:
        self.dashboard.apply(batch)
