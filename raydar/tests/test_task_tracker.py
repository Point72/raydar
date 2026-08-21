import time

import httpx
import pytest
import ray

from raydar import RayTaskTracker


@ray.remote
def do_some_work():
    time.sleep(0.1)
    return True


@pytest.mark.usefixtures("unittest_ray_cluster")
class TestRayTaskTracker:
    def test_construction_and_dataframe(self):
        task_tracker = RayTaskTracker(dashboard="local")
        try:
            assert len(task_tracker.namespace.split("-")) == 2
            refs = [do_some_work.remote() for _ in range(10)]
            task_tracker.process(refs)
            time.sleep(30)
            df = task_tracker.get_df()
            assert df[["name", "state"]].row(0) == ("do_some_work", "FINISHED")
        finally:
            task_tracker.dashboard.stop()

    def test_dashboard_is_off_by_default(self):
        task_tracker = RayTaskTracker()
        assert task_tracker.dashboard_url is None

    def test_dashboard_options_reach_the_dashboard(self):
        layout = {"sizes": [1], "viewers": {}}
        task_tracker = RayTaskTracker(dashboard="local", dashboard_options={"title": "custom", "layout": layout})
        try:
            dashboard = task_tracker.dashboard.dashboard
            dashboard.apply({"schemas": {"t": {"a": "integer"}}})
            assert dashboard.state.layout == layout
            assert "custom" in httpx.get(task_tracker.dashboard_url).text
        finally:
            task_tracker.dashboard.stop()

    def test_local_dashboard_serves_tables_pulled_from_the_actor(self):
        task_tracker = RayTaskTracker(dashboard="local")
        try:
            assert task_tracker.dashboard_url.startswith("http://127.0.0.1:")
            task_tracker.create_table("custom", {"a": "string", "b": "integer"})
            task_tracker.update_table("custom", [{"a": "foo", "b": 1}])

            tables = task_tracker.dashboard.dashboard.tables
            expected = ["custom", "task_tracker_data"]
            deadline = time.time() + 30
            while time.time() < deadline and sorted(tables.names()) != expected:
                time.sleep(0.5)

            assert sorted(tables.names()) == expected
            assert httpx.get(task_tracker.dashboard_url).status_code == 200
        finally:
            task_tracker.dashboard.stop()
