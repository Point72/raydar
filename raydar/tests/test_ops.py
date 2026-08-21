import pytest

from raydar.ops import OpBuffer


class TestOpBuffer:
    def test_drain_returns_schemas_and_updates(self):
        buffer = OpBuffer()
        buffer.new_table("t", {"a": "integer"})
        buffer.update("t", [{"a": 1}, {"a": 2}])

        batch = buffer.drain()
        assert batch == {"schemas": {"t": {"a": "integer"}}, "updates": {"t": [{"a": 1}, {"a": 2}]}, "cleared": []}

    def test_drain_replays_schemas_but_not_rows(self):
        buffer = OpBuffer()
        buffer.new_table("t", {"a": "integer"})
        buffer.update("t", [{"a": 1}])
        buffer.drain()

        batch = buffer.drain()
        assert batch["schemas"] == {"t": {"a": "integer"}}
        assert batch["updates"] == {}

    def test_update_accepts_a_single_row(self):
        buffer = OpBuffer()
        buffer.update("t", {"a": 1})
        assert buffer.drain()["updates"] == {"t": [{"a": 1}]}

    def test_new_table_does_not_replace_an_existing_schema(self):
        buffer = OpBuffer()
        buffer.new_table("t", {"a": "integer"})
        buffer.new_table("t", {"b": "string"})
        assert buffer.drain()["schemas"] == {"t": {"a": "integer"}}

    def test_rows_are_capped_per_table(self):
        buffer = OpBuffer(max_rows_per_table=3)
        buffer.update("t", [{"a": i} for i in range(10)])
        assert buffer.drain()["updates"]["t"] == [{"a": 7}, {"a": 8}, {"a": 9}]

    def test_clear_drops_pending_rows(self):
        buffer = OpBuffer()
        buffer.update("t", [{"a": 1}])
        buffer.clear("t")

        batch = buffer.drain()
        assert batch["updates"] == {}
        assert batch["cleared"] == ["t"]

    @pytest.mark.parametrize("batch", [{}, {"updates": {"t": []}}, {"schemas": None, "cleared": None}])
    def test_extend_tolerates_sparse_batches(self, batch):
        buffer = OpBuffer()
        buffer.extend(batch)
        assert buffer.drain() == {"schemas": {}, "updates": {}, "cleared": []}

    def test_extend_round_trips_a_drained_batch(self):
        source = OpBuffer()
        source.new_table("t", {"a": "integer"})
        source.update("t", [{"a": 1}])

        target = OpBuffer()
        target.extend(source.drain())
        assert target.drain() == {"schemas": {"t": {"a": "integer"}}, "updates": {"t": [{"a": 1}]}, "cleared": []}
