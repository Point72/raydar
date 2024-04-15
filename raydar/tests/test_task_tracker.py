import pytest
import ray
import requests
import time

from raydar import RayTaskTracker, setup_proxy_server


@ray.remote
def do_some_work():
    time.sleep(0.1)
    return True


@pytest.mark.usefixtures("unittest_ray_cluster")
class TestRayTaskTracker:
    def test_construction_and_dataframe(self):
        task_tracker = RayTaskTracker(enable_perspective_dashboard=True)
        assert len(task_tracker.namespace.split("-")) == 2
        refs = [do_some_work.remote() for _ in range(10)]
        task_tracker.process(refs)
        time.sleep(30)
        df = task_tracker.get_df()
        assert df[["name", "state"]].row(0) == ("do_some_work", "FINISHED")
        task_tracker.exit()

    def test_get_proxy_server(self):
        from raydar.dashboard.server import PerspectiveRayServer

        kwargs = dict(
            target=PerspectiveRayServer.bind(),
            name="webserver",
            route_prefix="/",
        )
        server = setup_proxy_server(**kwargs)
        server.remote("new", "test_table", dict(a="str", b="int", c="float", d="datetime"))
        time.sleep(2)
        server.remote("update", "test_table", [dict(a="foo", b=1, c=1.0, d=time.time())])
        time.sleep(2)
        response = requests.get("http://localhost:8000/tables")
        tables = eval(response.text)
        assert "test_table" in tables

    def test_scrape_prometheus_metrics(self):
        task_tracker = RayTaskTracker(
            enable_perspective_dashboard=True,
            scrape_prometheus_metrics=True,
        )
        time.sleep(30)
        response = requests.get("http://localhost:8000/tables")
        tables = eval(response.text)
        assert len(tables) > 100
        assert "ray_tasks" in tables
        assert "ray_actors" in tables
        assert "ray_resources" in tables
        task_tracker.exit()
