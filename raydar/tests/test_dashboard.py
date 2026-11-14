import json
import socket
import time
from datetime import UTC, date, datetime

import pytest
from perspective import PerspectiveError
from starlette.testclient import TestClient

from raydar.dashboard import Dashboard, LocalDashboard, TableHost, default_layout

SCHEMA = {"a": "integer", "b": "string"}


@pytest.fixture
def dashboard():
    return Dashboard(title="test")


@pytest.fixture(params=["UTC0", "UTC-8", "UTC+5"] if hasattr(time, "tzset") else [None])
def local_timezone(request, monkeypatch):
    if request.param is None:
        yield
        return
    try:
        with monkeypatch.context() as patch:
            patch.setenv("TZ", request.param)
            time.tzset()
            yield
    finally:
        time.tzset()


class TestDefaultLayout:
    def test_no_tables_yields_an_empty_layout(self):
        assert default_layout([]) == {}

    def test_each_table_gets_a_widget_and_a_viewer(self):
        layout = default_layout(["x", "y"])
        assert layout["layout"]["tabs"] == ["x", "y"]
        assert set(layout["panels"]) == {"x", "y"}
        assert layout["panels"]["x"]["table"] == "x"


class TestTableHost:
    def test_failed_table_creation_does_not_register_metadata(self):
        host = TableHost()
        with pytest.raises(PerspectiveError):
            host.new_table("t", {"a": "not-a-perspective-type"})

        assert host.names() == []
        assert "t" not in host._tables
        assert "t" not in host._temporal_columns

    def test_corrected_schema_can_retry_after_failed_table_creation(self):
        host = TableHost()
        with pytest.raises(PerspectiveError):
            host.new_table("t", {"a": "not-a-perspective-type"})

        assert host.new_table("t", SCHEMA)
        host.update("t", [{"a": 1, "b": "x"}])
        view = host._tables["t"].view()
        try:
            assert view.to_columns() == {"a": [1], "b": ["x"]}
        finally:
            view.delete()


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
        override = {"layout": {"type": "tab-layout", "tabs": []}, "panels": {}}
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
        assert dashboard.tables.total_rows() == 0
        assert dashboard.state.rows == "0"

    def test_update_of_an_unknown_table_raises(self, dashboard):
        with pytest.raises(KeyError):
            dashboard.apply({"updates": {"nope": [{"a": 1}]}})

    def test_a_failed_batch_still_syncs_what_landed(self, dashboard):
        with pytest.raises(KeyError):
            dashboard.apply(
                {
                    "schemas": {"t": SCHEMA},
                    "updates": {"t": [{"a": 1, "b": "x"}], "nope": [{"a": 1}]},
                }
            )

        # The good table landed, so it must be visible even though the batch raised.
        assert dashboard.state.tables == ["t"]
        assert dashboard.state.rows == "1"

    def test_failed_table_creation_does_not_publish_a_phantom_tab(self, dashboard):
        with pytest.raises(PerspectiveError):
            dashboard.apply({"schemas": {"existing": SCHEMA, "t": {"a": "not-a-perspective-type"}}})

        assert dashboard.state.tables == ["existing"]
        assert dashboard.tables.names() == ["existing"]

        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"existing": [{"a": 1, "b": "x"}], "t": [{"a": 2, "b": "y"}]}})
        assert dashboard.state.tables == ["existing", "t"]
        assert dashboard.state.rows == "2"

    def test_limit_caps_retained_rows(self):
        dashboard = Dashboard(limit=2)
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": i, "b": "x"} for i in range(5)]}})

        assert dashboard.tables.total_rows() == 2
        assert dashboard.state.rows == "2"

    def test_an_empty_batch_does_not_touch_the_synced_state(self, dashboard):
        dashboard.apply({"schemas": {"t": SCHEMA}})
        before = dashboard.state.model_copy(deep=True)

        # Schemas are replayed on every drain, so this is the steady-state batch.
        dashboard.apply({"schemas": {"t": SCHEMA}, "updates": {}, "cleared": []})
        assert dashboard.state == before

    def test_datetime_values_are_accepted(self, dashboard):
        # Perspective encodes rows as JSON, which rejects datetime outright.
        moment = datetime(2026, 8, 21, 12, 30, 15, tzinfo=UTC)
        dashboard.apply(
            {
                "schemas": {"t": {"when": "datetime", "day": "date"}},
                "updates": {"t": [{"when": moment, "day": date(2026, 8, 21)}]},
            }
        )

        assert dashboard.tables.total_rows() == 1
        stored = dashboard.tables._tables["t"].view().to_columns()["when"][0]
        assert stored == int(moment.timestamp() * 1000)

    def test_date_columns_preserve_calendar_days(self, dashboard, local_timezone):
        days = [date(2026, 8, 21), date(2024, 2, 29), date(1969, 12, 31)]
        dashboard.apply({"schemas": {"t": {"day": "date"}}, "updates": {"t": [{"day": day} for day in days]}})

        view = dashboard.tables._tables["t"].view()
        try:
            stored = view.to_columns()["day"]
        finally:
            view.delete()
        assert [datetime.fromtimestamp(value / 1000, UTC).date() for value in stored] == days

    def test_plain_dates_in_datetime_columns_use_local_midnight(self, dashboard, local_timezone):
        dashboard.apply({"schemas": {"t": {"when": "datetime"}}, "updates": {"t": [{"when": date(2026, 8, 21)}]}})

        view = dashboard.tables._tables["t"].view()
        try:
            assert view.to_columns()["when"] == [int(datetime(2026, 8, 21).timestamp() * 1000)]
        finally:
            view.delete()


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


class TestLocalDashboard:
    def test_poll_loop_survives_a_bad_batch(self):
        batches = [
            {"updates": {"missing": [{"a": 1}]}},  # unknown table -> KeyError
            {"schemas": {"t": SCHEMA}, "updates": {"t": [{"a": 1, "b": "x"}]}},
        ]
        local = LocalDashboard(drain=lambda: batches.pop(0) if batches else {}, poll_interval=0.05)
        local.start()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and local.dashboard.tables.names() != ["t"]:
                time.sleep(0.1)
            # The good batch only lands if the failed one did not kill the loop.
            assert local.dashboard.tables.names() == ["t"]
            assert local.dashboard.tables.total_rows() == 1
        finally:
            local.stop()

    def test_stop_is_idempotent_and_releases_the_port(self):
        local = LocalDashboard(drain=lambda: None, poll_interval=0.05)
        port = local.port
        local.start()
        local.stop()
        local.stop()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))

    def test_an_unstarted_dashboard_releases_its_socket(self):
        local = LocalDashboard(drain=lambda: None)
        port = local.port
        local.stop()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
