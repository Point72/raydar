import asyncio
import itertools
import logging
from collections.abc import Iterable
from typing import Literal

import coolname
import pandas as pd
import polars as pl
import ray
from ray.serve import shutdown

from ..ops import OpBuffer
from .schema import schema as default_schema

logger = logging.getLogger(__name__)

DashboardMode = Literal["local", "cluster"]

__all__ = ("AsyncMetadataTracker", "RayTaskTracker")


def get_callback_actor_name(name: str) -> str:
    return f"{name}_callback_actor"


@ray.remote(resources={"node:__internal_head__": 0.1}, num_cpus=0)
class AsyncMetadataTrackerCallback:
    """
    Intended to be constructed from an AsyncMetadataTracker actor, owning an attribute pointing
    back to that actor.
    """

    def __init__(self, name: str, namespace: str):
        self.actor = ray.get_actor(name, namespace)

    def process(self, obj_refs: Iterable[ray.ObjectRef]) -> None:
        """Processes an interable collection of ray.ObjectRefs.

        Iterates through the collection, finds completed references, and returns those references to the
        self.actor attribute via its .callback remote function.

        Args:
            obj_refs: An iterable collection of (possibly) in-progress ray object references
        """
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

    def exit(self) -> None:
        """Terminate this actor"""
        ray.actor.exit_actor()


@ray.remote(resources={"node:__internal_head__": 0.1}, num_cpus=0)
class AsyncMetadataTracker:
    def __init__(
        self,
        name: str,
        namespace: str,
        path: str | None = None,
        dashboard: DashboardMode | None = None,
        max_buffered_rows: int = 100_000,
    ):
        """An async Ray Actor Class to track task level metadata.

        This class constructs a AsyncMetadataTrackerCallback actor, which points back to this actor. Its process(...)
        method sends lists of object references to its AsyncMetadataTrackerCallback, which performs blocking ray.wait(...)
        calls on those object references, and calls this actor's callback(...) method as those tasks complete.

        Args:
            name: Ray actor name, used to construct its AsyncMetadataTrackerCallback actor attribute.
            namespace: Ray Namespace
            path: A Cloudpathlib.AnyPath, used for saving its internal polars DataFrame object.
            dashboard: "local" buffers table operations for a dashboard running outside the cluster to
                drain; "cluster" pushes them to a Ray Serve deployment; None disables the dashboard.
            max_buffered_rows: Per-table cap on rows held for a "local" dashboard to drain.
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
        self.dashboard_mode = dashboard
        self.pending_tasks = []
        self.perspective_table_name = f"{name}_data"
        self._buffer = None
        self._handle = None

        # WARNING: Do not move this import. Importing these modules elsewhere can cause
        # difficult to diagnose, "There is no current event loop in thread 'ray_client_server_" errors.
        asyncio.set_event_loop(asyncio.new_event_loop())
        from ray.util.state.api import StateApiClient

        self.client = StateApiClient(address=ray.get_runtime_context().gcs_address)

        if dashboard == "local":
            self._buffer = OpBuffer(max_rows_per_table=max_buffered_rows)
        elif dashboard == "cluster":
            from raydar.dashboard.serve import RaydarDeployment

            self._handle = ray.serve.run(RaydarDeployment.bind(), name="raydar", route_prefix="/")
        elif dashboard is not None:
            raise ValueError(f"Unknown dashboard mode: {dashboard!r}")

        if dashboard is not None:
            self.emit(
                {
                    "schemas": {
                        self.perspective_table_name: {
                            "task_id": "string",
                            "user_defined_metadata": "string",
                            "attempt_number": "integer",
                            "name": "string",
                            "state": "string",
                            "job_id": "string",
                            "actor_id": "float",
                            "type": "string",
                            "func_or_class_name": "string",
                            "parent_task_id": "string",
                            "node_id": "string",
                            "worker_id": "string",
                            "error_type": "string",
                            "language": "string",
                            "placement_group_id": "float",
                            "creation_time_ms": "datetime",
                            "start_time_ms": "datetime",
                            "end_time_ms": "datetime",
                            "error_message": "string",
                        }
                    }
                }
            )

    def emit(self, batch: dict) -> None:
        """Route a batch of table operations to whichever dashboard is configured."""
        if self._buffer is not None:
            self._buffer.extend(batch)
        elif self._handle is not None:
            self._handle.apply.remote(batch)

    def drain(self) -> dict | None:
        """Return buffered table operations for a dashboard running outside the cluster."""
        if self._buffer is None:
            return None
        return self._buffer.drain()

    def callback(self, tasks: Iterable[ray.ObjectRef]) -> None:
        """A remote function used by this actor's processor actor attribute. Will be called by a separate actor
        with a collection of ray object references once those ObjectReferences are not in the "RUNNING" or
        "PENDING" state.
        """
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

        if self.dashboard_mode is not None:
            self.publish_tasks(completed_tasks)

    def publish_tasks(self, completed_tasks) -> None:
        """Emit completed task metadata as rows for the dashboard's task table.

        Args:
            completed_tasks: A list of tuples of the form (ObjectReference, TaskMetadata), where the ObjectReferences are neither Running nor Pending Assignment.
        """
        data = [
            {
                "task_id": metadata.task_id,
                "attempt_number": metadata.attempt_number,
                "name": metadata.name,
                "state": metadata.state,
                "job_id": metadata.job_id,
                "actor_id": metadata.actor_id,
                "type": metadata.type,
                "func_or_class_name": metadata.func_or_class_name,
                "parent_task_id": metadata.parent_task_id,
                "node_id": metadata.node_id,
                "worker_id": metadata.worker_id,
                "error_type": metadata.error_type,
                "language": metadata.language,
                "placement_group_id": metadata.placement_group_id,
                "creation_time_ms": metadata.creation_time_ms,
                "start_time_ms": metadata.start_time_ms,
                "end_time_ms": metadata.end_time_ms,
                "error_message": metadata.error_message,
                "user_defined_metadata": self.user_defined_metadata.get(task.task_id().hex()),
            }
            for task, metadata in completed_tasks
        ]
        self.emit({"updates": {self.perspective_table_name: data}})

    async def process(self, obj_refs: Iterable[ray.ObjectRef], metadata: Iterable[str] | None = None, chunk_size: int = 25_000) -> None:
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

    def get_df(self) -> pl.DataFrame:
        """Retrieves an internally maintained dataframe of task related information pulled from the ray GCS"""
        self.df = pl.DataFrame(
            data={
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
            },
            schema_overrides=default_schema,
        )
        return self.df

    def save_df(self) -> None:
        """Saves the internally maintained dataframe of task related information from the ray GCS"""
        self.get_df()
        if self.path is not None and self.df is not None:
            logger.info(f"Writing DataFrame to {self.path}")
            self.df.write_parquet(self.path)
            return True
        return False

    def clear_df(self) -> None:
        """Clears the internally maintained dataframe of task related information from the ray GCS"""
        self.df = None
        self.finished_tasks = {}
        if self.dashboard_mode is not None:
            self.emit({"cleared": [self.perspective_table_name]})


class RayTaskTracker:
    def __init__(
        self,
        name: str = "task_tracker",
        namespace: str | None = None,
        dashboard: DashboardMode | None = None,
        dashboard_host: str = "127.0.0.1",
        dashboard_port: int = 0,
        dashboard_options: dict | None = None,
        poll_interval: float = 0.5,
        **kwargs,
    ):
        """A utility to construct AsyncMetadataTracker actors.

        Wraps several remote AsyncMetadataTracker functions in a ray.get() call for convenience.

        Args:
            name: The name used to construct a AsyncMetadataTracker, also used to form the name of its AsyncMetadataTrackerCallback.
            namespace: Ray namespace for the AsyncMetadataTracker and its AsyncMetadataTrackerCallback.
            dashboard: "local" serves the dashboard from this process and pulls updates over Ray,
                so the cluster needs no inbound port. "cluster" serves it from Ray Serve, which
                does. None disables the dashboard.
            dashboard_host: Interface the "local" dashboard binds.
            dashboard_port: Port the "local" dashboard binds, or 0 to pick a free one.
            dashboard_options: Forwarded to :class:`~raydar.dashboard.dashboard.Dashboard`
                (``title``, ``layout``, ``limit``).
            poll_interval: Seconds between "local" dashboard polls of the tracker actor.
            **kwargs: Forwarded to the AsyncMetadataTracker actor.
        """
        if namespace is None:
            namespace = coolname.generate_slug(2)
            logger.critical(f'No namespace provided, using namespace "{namespace}"')

        self.name = name
        self.namespace = namespace
        self.dashboard_mode = dashboard
        self.dashboard = None
        self.tracker = AsyncMetadataTracker.options(
            lifetime="detached",
            name=name,
            namespace=namespace,
            get_if_exists=True,
        ).remote(
            name=name,
            namespace=namespace,
            dashboard=dashboard,
            **kwargs,
        )

        if dashboard == "local":
            from raydar.dashboard import LocalDashboard

            self.dashboard = LocalDashboard(
                drain=lambda: ray.get(self.tracker.drain.remote()),
                host=dashboard_host,
                port=dashboard_port,
                poll_interval=poll_interval,
                **(dashboard_options or {}),
            )
            self.dashboard.start()

    @property
    def dashboard_url(self) -> str | None:
        """The URL of the local dashboard, or None when it is not running in this process."""
        return self.dashboard.url if self.dashboard else None

    def process(self, object_refs: Iterable[ray.ObjectRef], metadata: Iterable[str] | None = None, chunk_size: int = 25_000) -> None:
        """A helper function, to send this object's AsyncMetadataTracker actor a collection of object references to track"""
        self.tracker.process.remote(object_refs, metadata=metadata, chunk_size=chunk_size)

    def get_df(self, process_user_metadata_column=False) -> pl.DataFrame:
        """Fetches this object's AsyncMetadataTracker's internal dataframe object"""
        df = ray.get(self.tracker.get_df.remote())
        if process_user_metadata_column:
            user_metadata_frame = pl.from_pandas(pd.json_normalize(df["user_defined_metadata"].to_pandas()))
            df_with_user_metadata = pl.concat([df, user_metadata_frame], how="horizontal")
            return df_with_user_metadata
        return df

    def save_df(self) -> None:
        """Save the dataframe used by this object's AsyncMetadataTracker actor"""
        return ray.get(self.tracker.save_df.remote())

    def clear(self) -> None:
        """Clear the dataframe used by this object's AsyncMetadataTracker actor"""
        return ray.get(self.tracker.clear_df.remote())

    def create_table(self, table_name: str, table_schema: dict[str, str]) -> None:
        """Create a new perspective table on the dashboard"""
        self.tracker.emit.remote({"schemas": {table_name: table_schema}})

    def update_table(self, table_name: str, data: list[dict]) -> None:
        """Append rows to a perspective table on the dashboard"""
        self.tracker.emit.remote({"updates": {table_name: data}})

    def exit(self) -> None:
        """Perform cleanup tasks, kill associated actors, and shutdown."""
        if self.dashboard is not None:
            self.dashboard.stop()
            self.dashboard = None
        ray.kill(ray.get_actor(name=self.name, namespace=self.namespace))
        ray.kill(ray.get_actor(name=get_callback_actor_name(self.name), namespace=self.namespace))
        shutdown()
