"""The schema must match what Ray actually reports.

These run without a Ray cluster: the defect they guard is a type declaration,
and asserting it directly is both deterministic and immediate.
"""

import polars as pl
import pytest

from raydar.task_tracker.schema import schema

# Ray reports ids as hex strings, e.g. TaskState.actor_id.
RAY_ID = "22c21d18d3081db73e11271a01000000"

ID_COLUMNS = ("task_id", "actor_id", "job_id", "node_id", "worker_id", "parent_task_id", "placement_group_id")


@pytest.mark.parametrize("column", ID_COLUMNS)
def test_id_columns_hold_ray_hex_ids(column):
    # Declaring these numeric made get_df raise on any actor task and rendered
    # every id as 0.0 in the dashboard.
    frame = pl.DataFrame({column: [RAY_ID]}, schema_overrides={column: schema[column]})
    assert frame[column][0] == RAY_ID


@pytest.mark.parametrize("column", ID_COLUMNS)
def test_id_columns_are_declared_as_strings(column):
    assert schema[column] == pl.Utf8
