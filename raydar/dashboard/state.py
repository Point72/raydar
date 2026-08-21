"""The model the browser mirrors over transports."""

from pydantic import BaseModel, Field

__all__ = ("DashboardState", "default_layout")


class DashboardState(BaseModel):
    """State pushed to every connected browser.

    Bulk table data rides Perspective's own websocket; only this summary and the
    workspace layout travel over transports.
    """

    status: str = "Waiting for data"
    tables: list[str] = Field(default_factory=list)
    layout: dict = Field(default_factory=dict)
    rows: str = "0"
    updated: str = ""


def default_layout(tables: list[str]) -> dict:
    """A perspective-workspace layout showing one datagrid tab per table."""
    if not tables:
        return {}
    return {
        "sizes": [1],
        "detail": {"main": {"type": "tab-area", "widgets": list(tables), "currentIndex": 0}},
        "master": {"sizes": [], "widgets": []},
        "mode": "globalFilters",
        "viewers": {name: {"table": name, "plugin": "Datagrid", "title": name} for name in tables},
    }
