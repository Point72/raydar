import polars as pl

schema = {
    "task_id": pl.Utf8,
    "attempt_number": pl.Int64,
    "name": pl.Utf8,
    "state": pl.Utf8,
    "job_id": pl.Utf8,
    "actor_id": pl.Float32,
    "type": pl.Utf8,
    "func_or_class_name": pl.Utf8,
    "parent_task_id": pl.Utf8,
    "node_id": pl.Utf8,
    "worker_id": pl.Utf8,
    "error_type": pl.Utf8,
    "language": pl.Utf8,
    "required_resources": pl.Struct([pl.Field("CPU", pl.Float64)]),
    "runtime_env_info": pl.Struct(
        [
            pl.Field("serialized_runtime_env", pl.Utf8),
            pl.Field(
                "runtime_env_config",
                pl.Struct(
                    [
                        pl.Field("setup_timeout_seconds", pl.Int64),
                        pl.Field("eager_install", pl.Boolean),
                    ]
                ),
            ),
        ]
    ),
    "placement_group_id": pl.Float32,
    "events": pl.List(pl.Struct([pl.Field("state", pl.Utf8), pl.Field("created_ms", pl.Float64)])),
    "profiling_data": pl.Struct(
        [
            pl.Field("component_type", pl.Utf8),
            pl.Field("component_id", pl.Utf8),
            pl.Field("node_ip_address", pl.Utf8),
            pl.Field(
                "events",
                pl.List(
                    pl.Struct(
                        [
                            pl.Field(
                                "start_time",
                                pl.Datetime(time_unit="ms", time_zone="America/New_York"),
                            ),
                            pl.Field(
                                "end_time",
                                pl.Datetime(time_unit="ms", time_zone="America/New_York"),
                            ),
                            pl.Field(
                                "extra_data",
                                pl.Struct(
                                    [
                                        pl.Field("name", pl.Utf8),
                                        pl.Field("task_id", pl.Utf8),
                                    ]
                                ),
                            ),
                            pl.Field("event_name", pl.Utf8),
                        ]
                    )
                ),
            ),
        ]
    ),
    "creation_time_ms": pl.Datetime(time_unit="ms", time_zone="America/New_York"),
    "start_time_ms": pl.Datetime(time_unit="ms", time_zone="America/New_York"),
    "end_time_ms": pl.Datetime(time_unit="ms", time_zone="America/New_York"),
    "task_log_info": pl.Struct(
        [
            pl.Field("stdout_file", pl.Utf8),
            pl.Field("stderr_file", pl.Utf8),
            pl.Field("stdout_start", pl.Int64),
            pl.Field("stdout_end", pl.Int64),
            pl.Field("stderr_start", pl.Int64),
            pl.Field("stderr_end", pl.Int64),
        ]
    ),
    "error_message": pl.Utf8,
}
