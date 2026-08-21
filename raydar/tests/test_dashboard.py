import json

import pytest
from starlette.testclient import TestClient

from raydar.dashboard import Dashboard, default_layout

SCHEMA = {"a": "integer", "b": "string"}


@pytest.fixture
def dashboard():
    return Dashboard(title="test")


class TestDefaultLayout:
    def test_no_tables_yields_an_empty_layout(self):
        assert default_layout([]) == {}

    def test_each_table_gets_a_widget_and_a_viewer(self):
        layout = default_layout(["x", "y"])
        assert layout["detail"]["main"]["widgets"] == ["x", "y"]
        assert set(layout["viewers"]) == {"x", "y"}
        assert layout["viewers"]["x"]["table"] == "x"


class TestDashboard:
    def test_apply_creates_tables_and_counts_rows(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": 1, "b": "x"}]}})

        assert dashboard.tables.names() == ["t"]
        assert dashboard.state.tables == ["t"]
        assert dashboard.state.rows == "1"
        assert dashboard.state.status == "Live"

    def test_state_starts_empty(self, dashboard):
        assert dashboard.state.tables == []
        assert dashboard.state.layout == {}
        assert dashboard.state.status == "Waiting for data"

    def test_layout_follows_the_tables(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}})
        assert dashboard.state.layout == default_layout(["t"])

    def test_layout_override_wins(self):
        override = {"sizes": [1], "viewers": {}}
        dashboard = Dashboard(layout=override)
        dashboard.apply({"schemas": {"t": SCHEMA}})
        assert dashboard.state.layout == override

    def test_repeated_schemas_do_not_recreate_tables(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": 1, "b": "x"}]}})
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": 2, "b": "y"}]}})
        assert dashboard.state.rows == "2"

    def test_clear_empties_the_table(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": 1, "b": "x"}]}})
        dashboard.apply({"cleared": ["t"]})
        assert dashboard.tables.names() == ["t"]

    def test_update_of_an_unknown_table_raises(self, dashboard):
        with pytest.raises(KeyError):
            dashboard.apply({"updates": {"nope": [{"a": 1}]}})

    def test_limit_is_applied_to_new_tables(self):
        dashboard = Dashboard(limit=2)
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": i, "b": "x"} for i in range(5)]}})
        assert dashboard.tables.names() == ["t"]


class TestDashboardApp:
    def test_page_and_assets_are_served(self, dashboard):
        with TestClient(dashboard.app) as client:
            page = client.get("/")
            assert page.status_code == 200
            # spaday's source/installed asset detection is pinned; a regression there 404s the runtime.
            for asset in ("/js/cdn/index.js", "/components/perspective/cdn/index.js", "/components/webawesome/cdn/index.js"):
                assert client.get(asset).status_code == 200, asset

    def test_tree_wires_the_panel_to_the_state_model(self, dashboard):
        with TestClient(dashboard.app) as client:
            tree = json.dumps(client.get("/tree.json").json())
        assert "perspective-panel" in tree
        for path in ("rd.tables", "rd.layout", "rd.status"):
            assert path in tree

    def test_state_is_pushed_over_the_transports_socket(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}})
        with TestClient(dashboard.app) as client, client.websocket_connect("/ws") as ws:
            snapshot = json.loads(ws.receive_text())
        assert snapshot["t"] == "snapshot"
        assert snapshot["type"] == "DashboardState"

    def test_perspective_has_its_own_socket(self, dashboard):
        with TestClient(dashboard.app) as client, client.websocket_connect("/perspective") as ws:
            assert ws is not None
