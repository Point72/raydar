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

    def test_a_single_task_is_still_recorded(self, trackers):
        # One task completes in one wait round, so the tracker gets exactly one
        # callback. The GCS has not published the task's state that early, so
        # nothing was recorded until the processor learned to wait for it.
        task_tracker = trackers(dashboard="local")
        task_tracker.process([do_some_work.remote()])

        df = wait_for(task_tracker.get_df, lambda d: not d.is_empty(), timeout=90)
        assert not df.is_empty(), "the only task the tracker was given went unrecorded"
        assert df[["name", "state"]].row(0) == ("do_some_work", "FINISHED")

    def test_callback_reports_tasks_the_gcs_has_not_published(self, trackers):
        # The caller cannot ask the tracker whether work is outstanding: it is an
        # async actor, so a separate query can be answered before the callback it
        # was meant to observe has run. The callback has to say so itself.
        task_tracker = trackers(dashboard="local")
        ref = do_some_work.remote()
        ray.wait([ref], fetch_local=False)

        tracker = task_tracker.tracker
        pending = ray.get(tracker.callback.remote([ref]))
        assert isinstance(pending, bool), "callback must report whether it still has work"

        deadline = time.time() + 60
        while pending and time.time() < deadline:
            time.sleep(0.5)
            pending = ray.get(tracker.callback.remote([]))

        assert not pending, "tracker never resolved the task"
        assert not ray.get(tracker.get_df.remote()).is_empty()

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
