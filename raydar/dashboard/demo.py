"""A runnable example of the local dashboard: `python -m raydar.dashboard.demo`.

The dashboard is served from this process and pulls updates from the tracker
actor over Ray, so the cluster needs no inbound port.
"""

import random
import time
from datetime import UTC, datetime

import ray

from ..task_tracker import RayTaskTracker

TABLE = "demo"
SCHEMA = {
    "start": "datetime",
    "end": "datetime",
    "runtime": "float",
    "backoff": "float",
    "random": "float",
}


@ray.remote
def demo_job(backoff: float) -> dict:
    start = datetime.now(tz=UTC)
    time.sleep(backoff)
    end = datetime.now(tz=UTC)
    return {
        "start": start,
        "end": end,
        "runtime": (end - start).total_seconds(),
        "backoff": backoff,
        "random": random.random(),
    }


if __name__ == "__main__":
    ray.init()

    task_tracker = RayTaskTracker(namespace="raydar-demo", dashboard="local")
    task_tracker.create_table(TABLE, SCHEMA)
    print(f"raydar dashboard: {task_tracker.dashboard_url}")

    try:
        while True:
            ref = demo_job.remote(backoff=random.random())
            task_tracker.process([ref])
            task_tracker.update_table(TABLE, [ray.get(ref)])
            time.sleep(0.5)
    except KeyboardInterrupt:
        task_tracker.exit()
