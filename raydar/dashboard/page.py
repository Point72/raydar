"""The raydar page, authored as a spaday component tree."""

from spaday import cond, element, field, obj
from spaday_perspective import PerspectivePanel
from spaday_webawesome import WaBadge, WaSwitch

__all__ = ("STYLES", "build_page")

STYLES = """
<style>
  :root { color-scheme: light dark; }
  html, body { height: 100%; margin: 0; }
  /* Neutral greys matched to Perspective's own themes, whose dark viewer is #242526.
     A tinted palette here reads as a colour cast against the grid. */
  .rd { display: flex; flex-direction: column; height: 100vh; box-sizing: border-box;
    background: #f5f5f5; color: #161616; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
  .rd.wa-dark { background: #242526; color: #e4e6eb; }
  .rd-header { display: flex; align-items: center; gap: 1rem; flex: none; height: 3rem; padding: 0 1rem;
    border-bottom: 1px solid #e0e0e0; background: rgba(255, 255, 255, .85); }
  .rd.wa-dark .rd-header { border-bottom-color: #3a3b3c; background: rgba(28, 29, 30, .9); }
  .rd-brand { font-size: 1rem; font-weight: 800; letter-spacing: -.03em; }
  .rd-version { color: #6b6b6b; font-size: .75rem; }
  .rd.wa-dark .rd-version { color: #9a9da1; }
  .rd-metrics { display: flex; align-items: center; gap: .5rem; margin-left: auto; font-size: .8rem; }
  .rd-workspace { flex: 1 1 auto; min-height: 0; }
  #raydar-workspace { display: block; width: 100%; height: 100%; }
</style>
"""


def build_page(title: str, version: str):
    """Build the component tree.

    ``rd.*`` fields come from the transports-hosted :class:`~raydar.dashboard.state.DashboardState`;
    ``dark`` is a client-only store field, so the theme toggle needs no round trip.
    """
    panel = (
        PerspectivePanel(id="raydar-workspace")
        .compute("theme", cond(field("dark"), "dark", "light"))
        .compute(
            "config",
            obj({"ws_url": "/perspective", "tables": field("rd.tables"), "layout": field("rd.layout")}),
        )
    )

    header = element(
        "header",
        element("span", class_="rd-brand").text(title),
        element("span", class_="rd-version").text(f"v{version}"),
        element(
            "div",
            WaBadge(variant="brand").bind("textContent", "rd.status"),
            element("span").bind("textContent", "rd.rows"),
            element("span").text("rows"),
            element("span", class_="rd-version").bind("textContent", "rd.updated"),
            WaSwitch().bind("checked", "dark", mode="two-way"),
            element("span").text("Dark"),
            class_="rd-metrics",
        ),
        class_="rd-header",
    )

    return element(
        "div",
        header,
        element("section", panel, class_="rd-workspace"),
    ).compute("class", cond(field("dark"), "rd wa-dark", "rd"))
