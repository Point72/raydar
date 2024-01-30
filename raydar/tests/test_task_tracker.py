import pytest
import ray
import time

from raydar import RayTaskTracker


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
