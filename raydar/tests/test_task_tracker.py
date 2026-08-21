import logging
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


@pytest.fixture
def trackers():
    """Build trackers and release them afterwards.

    Each RayTaskTracker pins 0.2 of the head node's 1.0 `node:__internal_head__`
    budget across its two detached actors, so leaving them alive starves the
    fifth tracker in a module and its metadata never arrives.
    """
    created = []

    def make(**kwargs):
        tracker = RayTaskTracker(**kwargs)
        created.append(tracker)
        return tracker

    yield make

    for tracker in created:
        try:
            tracker.exit()
        except Exception:
            logging.getLogger(__name__).exception("Failed to release tracker %s", tracker.name)


@pytest.mark.usefixtures("unittest_ray_cluster")
class TestRayTaskTracker:
    def test_construction_and_dataframe(self, trackers):
        task_tracker = trackers(dashboard="local")
        assert len(task_tracker.namespace.split("-")) == 2
        refs = [do_some_work.remote() for _ in range(10)]
        task_tracker.process(refs)

        # Metadata arrives via GCS polling, so wait on the result rather than
        # on a fixed sleep, which was slow on a fast box and flaky on a slow one.
        df = wait_for(task_tracker.get_df, lambda d: not d.is_empty())
        assert not df.is_empty(), "tracker recorded no finished tasks"
        assert df[["name", "state"]].row(0) == ("do_some_work", "FINISHED")

    def test_dashboard_is_off_by_default(self, trackers):
        task_tracker = trackers()
        assert task_tracker.dashboard_url is None

    def test_actor_task_ids_survive_as_strings(self, trackers):
        # Ray reports actor_id as a hex string. Declaring it numeric made get_df
        # raise and rendered every id as 0.0 in the dashboard.
        task_tracker = trackers(dashboard="local")
        actor = SomeActor.remote()
        refs = [actor.do_some_work.remote() for _ in range(3)]
        task_tracker.process(refs)
        ray.get(refs)

        df = wait_for(task_tracker.get_df, lambda d: not d.is_empty())
        assert not df.is_empty(), "tracker recorded no finished actor tasks"

        actor_ids = [a for a in df["actor_id"].to_list() if a]
        assert actor_ids, "actor_id was not recorded"
        assert all(isinstance(a, str) and int(a, 16) for a in actor_ids)

    def test_dashboard_options_reach_the_dashboard(self, trackers):
        layout = {"sizes": [1], "viewers": {}}
        task_tracker = trackers(dashboard="local", dashboard_options={"title": "custom", "layout": layout})
        dashboard = task_tracker.dashboard.dashboard
        dashboard.apply({"schemas": {"t": {"a": "integer"}}})
        assert dashboard.state.layout == layout
        assert "custom" in httpx.get(task_tracker.dashboard_url).text

    def test_local_dashboard_serves_tables_pulled_from_the_actor(self, trackers):
        task_tracker = trackers(dashboard="local")
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
