import asyncio
import coolname
import datetime
import itertools
import logging
import os
import pandas as pd
import polars as pl
import ray
import re
import requests
import time
from collections import defaultdict
from dataclasses import dataclass
from packaging.version import Version
from prometheus_client.openmetrics import parser
from ray.serve import shutdown

from .schema import schema as default_schema

logger = logging.getLogger(__name__)

__all__ = ("AsyncMetadataTracker", "RayTaskTracker")


def get_callback_actor_name(name: str) -> str:
    return f"{name}_callback_actor"


@ray.remote(resources={"node:__internal_head__": 0.1}, num_cpus=0)
class AsyncMetadataTrackerCallback:
    """
    Intended to be constructed from an AsyncMetadataTracker actor, owning an attribute pointing
    back to that actor.
    """

    def __init__(self, name, namespace):
        self.actor = ray.get_actor(name, namespace)

    def process(self, obj_refs):
        active_tasks = set(obj_refs)
        while len(active_tasks) > 0:
            finished_tasks = []
            for obj_ref in obj_refs:
                if obj_ref in active_tasks:
                    done, _ = ray.wait([obj_ref], timeout=0.0, fetch_local=False)
                    if done:
                        active_tasks.remove(done[0])
                        finished_tasks.append(done[0])
            if len(finished_tasks) > 0:
                self.actor.callback.remote(finished_tasks)
        return

    def exit(self):
        ray.actor.exit_actor()


@ray.remote(resources={"node:__internal_head__": 0.1}, num_cpus=0)
class AsyncMetadataTracker:
    def __init__(
        self,
        name,
        namespace,
        path=None,
        enable_perspective_dashboard=False,
        scrape_prometheus_metrics=False,
    ):
        """An async Ray Actor Class to track task level metadata.

        This class constructs a AsyncMetadataTrackerCallback actor, which points back to this actor. Its process(...)
        method sends lists of object references to its AsyncMetadataTrackerCallback, which performs blocking ray.wait(...)
        calls on those object references, and calls this actor's callback(...) method as those tasks complete.

        Args:
            name: Ray actor name, used to construct its AsyncMetadataTrackerCallback actor attribute.
            namespace: Ray Namespace
            path: A Cloudpathlib.AnyPath, used for saving its internal polars DataFrame object.
            enable_perspective_dashboard: To enable an experimental perspective dashboard.

        """
        logger.info(f"Initializing an AsyncMetadataTracker in namespace {namespace} with name {name}.")
        # Passing 'self' to the AsyncMetadataTrackerCallback converts this actor class to a
        # modify_Class.<locals>.Class object. So for now, we pass the name and
        # namespace used to construct this actor to its AsyncMetadataTrackerCallback.
        self.processor = AsyncMetadataTrackerCallback.options(
            name=get_callback_actor_name(name),
            namespace=namespace,
            lifetime="detached",
            get_if_exists=True,
        ).remote(name, namespace)
        self.path = path
        self.df = None
        self.finished_tasks = {}
        self.user_defined_metadata = {}
        self.perspective_dashboard_enabled = enable_perspective_dashboard
        self.pending_tasks = []
        self.perspective_table_name = f"{name}_data"

        # WARNING: Do not move this import. Importing these modules elsewhere can cause
        # difficult to diagnose, "There is no current event loop in thread 'ray_client_server_" errors.
        asyncio.set_event_loop(asyncio.new_event_loop())
        from ray.util.state.api import StateApiClient

        self.client = StateApiClient(address=ray.get_runtime_context().gcs_address)

        if self.perspective_dashboard_enabled:
            from raydar.dashboard.server import PerspectiveProxyRayServer, PerspectiveRayServer

            kwargs = dict(
                target=PerspectiveRayServer.bind(),
                name="webserver",
                route_prefix="/",
            )
            if Version(ray.__version__) < Version("2.10"):
                kwargs["port"] = os.environ.get("RAYDAR_PORT", 8000)
            self.webserver = ray.serve.run(**kwargs)

            self.proxy_server = ray.serve.run(
                PerspectiveProxyRayServer.bind(self.webserver),
                name="proxy",
                route_prefix="/proxy",
            )
            self.proxy_server.remote(
                "new",
                self.perspective_table_name,
                {
                    "task_id": "str",
                    "user_defined_metadata": "str",
                    "attempt_number": "int",
                    "name": "str",
                    "state": "str",
                    "job_id": "str",
                    "actor_id": "float",
                    "type": "str",
                    "func_or_class_name": "str",
                    "parent_task_id": "str",
                    "node_id": "str",
                    "worker_id": "str",
                    "error_type": "str",
                    "language": "str",
                    "placement_group_id": "float",
                    "creation_time_ms": "datetime",
                    "start_time_ms": "datetime",
                    "end_time_ms": "datetime",
                    "error_message": "str",
                },
            )
            if scrape_prometheus_metrics:
                self.__scraping_job = self.scrape_prometheus_metrics()

    def scrape_prometheus_metrics(self):
        @dataclass
        class ParsedOpenMetricsData:
            metric_name: str
            metric_description: str
            metric_type: str
            metric_value: str
            metric_metadata: str

        def parse_response(text):
            parsed_data = []
            metric_name = None
            metric_description = None
            for line in text.split("\n"):
                if len(line) > 0:
                    if line.startswith("# HELP "):
                        metric_description = " ".join(line.split(" ")[3:])
                    elif line.startswith("# TYPE "):
                        _, _, metric_name, metric_type = line.split(" ")
                    else:
                        matches = re.search(r".*\{(.*)\}(.*)", line)
                        if matches is not None:
                            metric_metadata, metric_value = matches.groups()
                            metric_metadata = parser._parse_labels_with_state_machine(metric_metadata)[0]
                        else:
                            _, metric_value = line.split(" ")
                            metric_metadata = dict()
                        parsed_data.append(
                            ParsedOpenMetricsData(
                                metric_name=metric_name,
                                metric_description=metric_description,
                                metric_type=metric_type,
                                metric_value=eval(metric_value),
                                metric_metadata=metric_metadata,
                            )
                        )
            return parsed_data

        @ray.remote
        def scrape():
            metrics = set()
            while True:
                time.sleep(2)
                for node in ray.nodes():
                    all_values = defaultdict(list)
                    if node.get("Alive", False):
                        node_manager_address = node.get("NodeManagerAddress")
                        metrics_export_port = node.get("MetricsExportPort")
                        response = requests.get(f"http://{node_manager_address}:{metrics_export_port}/metrics")
                        if response.status_code == 200:
                            parsed_values = parse_response(response.text)
                            for parsed_value in parsed_values:
                                data = dict(
                                    metric_name=parsed_value.metric_name,
                                    metric_description=parsed_value.metric_description,
                                    metric_type=parsed_value.metric_type,
                                    metric_value=parsed_value.metric_value,
                                    timestamp=datetime.datetime.now(),
                                )
                                for key, value in parsed_value.metric_metadata.items():
                                    data[key] = value
                                all_values[parsed_value.metric_name].append(data)

                for key, values in all_values.items():
                    if key not in metrics:
                        metrics.add(key)
                        self.proxy_server.remote("new", key, values)
                    else:
                        self.proxy_server.remote("update", key, values)

        return scrape.remote()

    def get_proxy_server(self):
        if self.proxy_server:
            return self.proxy_server
        raise Exception("This task_tracker has no active proxy_server.")

    def callback(self, tasks):
        # WARNING: Do not move this import. Importing these modules elsewhere can cause
        # difficult to diagnose, "There is no current event loop in thread 'ray_client_server_" errors.
        asyncio.set_event_loop(asyncio.new_event_loop())
        from ray.util.state.common import GetApiOptions, StateResource

        def metadata_filter(task) -> bool:
            return task is not None and task.state not in {
                "NIL",
                "PENDING_ARGS_AVAIL",
                "PENDING_NODE_ASSIGNMENT",
                "PENDING_OBJ_STORE_MEM_AVAIL",
                "PENDING_ARGS_FETCH",
                "SUBMITTED_TO_WORKER",
                "RUNNING",
                "RUNNING_IN_RAY_GET",
                "RUNNING_IN_RAY_WAIT",
            }

        all_tasks = itertools.chain(tasks, self.pending_tasks)
        task_metadata = [
            (
                task,
                self.client.get(
                    resource=StateResource.TASKS,
                    id=task.task_id().hex(),
                    options=GetApiOptions(),
                ),
            )
            for task in all_tasks
        ]
        delayed_tasks = [task for task, metadata in task_metadata if not metadata_filter(metadata)]
        self.pending_tasks = delayed_tasks
        completed_tasks = [(task, metadata) for task, metadata in task_metadata if metadata_filter(metadata)]

        for task, metadata in completed_tasks:
            self.finished_tasks[task.task_id().hex()] = metadata

        if self.perspective_dashboard_enabled:
            self.update_perspective_dashboard(completed_tasks)

    def update_perspective_dashboard(self, completed_tasks):
        """A helper function, which updates this actor's proxy_server attribute with processed data.

        That proxy_server serves perspective tables which anticipate the data formats we provide.

        Args:
            completed_tasks: A list of tuples of the form (ObjectReference, TaskMetadata), where the
                             ObjectReferences are neither Running nor Pending Assignment.

        """
        data = [
            dict(
                task_id=metadata.task_id,
                attempt_number=metadata.attempt_number,
                name=metadata.name,
                state=metadata.state,
                job_id=metadata.job_id,
                actor_id=metadata.actor_id,
                type=metadata.type,
                func_or_class_name=metadata.func_or_class_name,
                parent_task_id=metadata.parent_task_id,
                node_id=metadata.node_id,
                worker_id=metadata.worker_id,
                error_type=metadata.error_type,
                language=metadata.language,
                placement_group_id=metadata.placement_group_id,
                creation_time_ms=metadata.creation_time_ms,
                start_time_ms=metadata.start_time_ms,
                end_time_ms=metadata.end_time_ms,
                error_message=metadata.error_message,
                user_defined_metadata=self.user_defined_metadata.get(task.task_id().hex()),
            )
            for task, metadata in completed_tasks
        ]
        self.proxy_server.remote("update", self.perspective_table_name, data)

    async def process(self, obj_refs, metadata=None, chunk_size=25_000):
        """An asynchronous function to process a collection of Ray object references.

        Sends sub-collections of object references of size chunk_size to its AsyncMetadataTrackerCallback actor.

        Args:
            obj_refs: A List of Ray object references.
            metadata: An optional list of equal size, of json-strings for each object reference.
            chunk_size: The maximum number of tasks to pass to its AsyncMetadataTrackerCallback at a time.
        """
        if metadata:
            for obj, info in zip(obj_refs, metadata):
                self.user_defined_metadata[obj.task_id().hex()] = info
        for i in range(0, len(obj_refs), chunk_size):
            self.processor.process.remote(obj_refs[i : i + chunk_size])

    def get_df(self):
        self.df = pl.DataFrame(
            data={
                # fmt: off
                "task_id": [task.task_id for task in self.finished_tasks.values()],
                "user_defined_metadata": [self.user_defined_metadata.get(task.task_id) for task in self.finished_tasks.values()],
                "attempt_number": [task.attempt_number for task in self.finished_tasks.values()],
                "name": [task.name for task in self.finished_tasks.values()],
                "state": [task.state for task in self.finished_tasks.values()],
                "job_id": [task.job_id for task in self.finished_tasks.values()],
                "actor_id": [task.actor_id for task in self.finished_tasks.values()],
                "type": [task.type for task in self.finished_tasks.values()],
                "func_or_class_name": [task.func_or_class_name for task in self.finished_tasks.values()],
                "parent_task_id": [task.parent_task_id for task in self.finished_tasks.values()],
                "node_id": [task.node_id for task in self.finished_tasks.values()],
                "worker_id": [task.worker_id for task in self.finished_tasks.values()],
                "error_type": [task.error_type for task in self.finished_tasks.values()],
                "language": [task.language for task in self.finished_tasks.values()],
                "required_resources": [task.required_resources for task in self.finished_tasks.values()],
                "runtime_env_info": [task.runtime_env_info for task in self.finished_tasks.values()],
                "placement_group_id": [task.placement_group_id for task in self.finished_tasks.values()],
                "events": [task.events for task in self.finished_tasks.values()],
                "profiling_data": [task.profiling_data for task in self.finished_tasks.values()],
                "creation_time_ms": [task.creation_time_ms for task in self.finished_tasks.values()],
                "start_time_ms": [task.start_time_ms for task in self.finished_tasks.values()],
                "end_time_ms": [task.end_time_ms for task in self.finished_tasks.values()],
                "task_log_info": [task.task_log_info for task in self.finished_tasks.values()],
                "error_message": [task.error_message for task in self.finished_tasks.values()],
                # fmt: on
            },
            schema_overrides=default_schema,
        )
        return self.df

    def save_df(self):
        self.get_df()
        if self.path is not None and self.df is not None:
            logger.info(f"Writing DataFrame to {self.path}")
            self.df.write_parquet(self.path)
            return True
        return False

    def clear_df(self):
        self.df = None
        self.finished_tasks = {}
        if self.perspective_dashboard_enabled:
            self.proxy_server.remote("clear", self.perspective_table_name, None)


class RayTaskTracker:
    def __init__(self, name: str = "task_tracker", namespace: str = None, **kwargs):
        """A utility to construct AsyncMetadataTracker actors.

        Wraps several remote AsyncMetadataTracker functions in a ray.get() call for convenience.

        Args:
            Optional[name]: The named used to construct a AsyncMetadataTracker, also used to form the name of its AsyncMetadataTrackerCallback.
            Optional[namespace]: Ray namespace for the AsyncMetadataTracker and its AsyncMetadataTrackerCallback.
        """
        if namespace is None:
            namespace = coolname.generate_slug(2)
            logger.critical(f'No namespace provided, using namespace "{namespace}"')

        self.name = name
        self.namespace = namespace
        self.tracker = AsyncMetadataTracker.options(
            lifetime="detached",
            name=name,
            namespace=namespace,
            get_if_exists=True,
        ).remote(
            name=name,
            namespace=namespace,
            **kwargs,
        )

    def process(self, object_refs, metadata=None, chunk_size=25_000):
        self.tracker.process.remote(object_refs, metadata=metadata, chunk_size=chunk_size)

    def get_df(self, process_user_metadata_column=False):
        df = ray.get(self.tracker.get_df.remote())
        if process_user_metadata_column:
            user_metadata_frame = pl.from_pandas(pd.json_normalize(df["user_defined_metadata"].to_pandas()))
            df_with_user_metadata = pl.concat([df, user_metadata_frame], how="horizontal")
            return df_with_user_metadata
        return df

    def save_df(self):
        return ray.get(self.tracker.save_df.remote())

    def clear(self):
        return ray.get(self.tracker.clear_df.remote())

    def proxy_server(self):
        return ray.get(self.tracker.get_proxy_server.remote())

    def exit(self):
        ray.kill(ray.get_actor(name=self.name, namespace=self.namespace))
        ray.kill(ray.get_actor(name=get_callback_actor_name(self.name), namespace=self.namespace))
        shutdown()
