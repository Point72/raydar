import time

import httpx
import pytest
import ray

from raydar import RayTaskTracker


@ray.remote
def do_some_work():
    time.sleep(0.1)
    return True


@ray.remote
class SomeActor:
    def do_some_work(self):
        time.sleep(0.1)
        return True


def wait_for(fetch, ready, timeout=120, interval=0.5):
    """Poll `fetch` until `ready` accepts the value, then return it."""
    deadline = time.time() + timeout
    value = fetch()
    while not ready(value) and time.time() < deadline:
        time.sleep(interval)
        value = fetch()
    return value


@pytest.mark.usefixtures("unittest_ray_cluster")
class TestRayTaskTracker:
    def test_construction_and_dataframe(self):
        task_tracker = RayTaskTracker(dashboard="local")
        try:
            assert len(task_tracker.namespace.split("-")) == 2
            refs = [do_some_work.remote() for _ in range(10)]
            task_tracker.process(refs)

            # Metadata arrives via GCS polling, so wait on the result rather than
            # on a fixed sleep, which was slow on a fast box and flaky on a slow one.
            df = wait_for(task_tracker.get_df, lambda d: not d.is_empty())
            assert not df.is_empty(), "tracker recorded no finished tasks"
            assert df[["name", "state"]].row(0) == ("do_some_work", "FINISHED")
        finally:
            task_tracker.dashboard.stop()

    def test_dashboard_is_off_by_default(self):
        task_tracker = RayTaskTracker()
        assert task_tracker.dashboard_url is None

    def test_actor_task_ids_survive_as_strings(self):
        # Ray reports actor_id as a hex string. Declaring it numeric made get_df
        # raise and rendered every id as 0.0 in the dashboard.
        task_tracker = RayTaskTracker(dashboard="local")
        try:
            actor = SomeActor.remote()
            refs = [actor.do_some_work.remote() for _ in range(3)]
            task_tracker.process(refs)
            ray.get(refs)

            df = wait_for(task_tracker.get_df, lambda d: not d.is_empty())
            assert not df.is_empty(), "tracker recorded no finished actor tasks"

            actor_ids = [a for a in df["actor_id"].to_list() if a]
            assert actor_ids, "actor_id was not recorded"
            assert all(isinstance(a, str) and int(a, 16) for a in actor_ids)
        finally:
            task_tracker.dashboard.stop()

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
            names = wait_for(lambda: sorted(tables.names()), lambda n: n == expected, timeout=60)
            assert names == expected

            # Wait on the row too: names alone pass before the update is applied.
            rows = wait_for(lambda: tables._tables["custom"].size(), lambda n: n > 0, timeout=60)
            assert rows == 1
            assert httpx.get(task_tracker.dashboard_url).status_code == 200
        finally:
            task_tracker.dashboard.stop()
