import pytest
from perspective import PerspectiveError

from raydar.dashboard import Dashboard, TableHost

INVALID_SCHEMA = {"price": "not-a-perspective-type"}
VALID_SCHEMA = {"price": "float"}


def test_failed_table_creation_does_not_register_metadata():
    host = TableHost()

    with pytest.raises(PerspectiveError, match="Unknown type"):
        host.new_table("quotes", INVALID_SCHEMA)

    assert host.names() == []
    assert "quotes" not in host._tables
    assert "quotes" not in host._temporal_columns


def test_corrected_schema_can_retry_after_failed_table_creation():
    host = TableHost()

    with pytest.raises(PerspectiveError, match="Unknown type"):
        host.new_table("quotes", INVALID_SCHEMA)

    assert host.new_table("quotes", VALID_SCHEMA)
    host.update("quotes", [{"price": 101.25}])
    assert host.names() == ["quotes"]
    assert host.total_rows() == 1
    assert host._tables["quotes"].view().to_columns() == {"price": [101.25]}


def test_failed_table_creation_does_not_publish_a_phantom_tab():
    dashboard = Dashboard()

    with pytest.raises(PerspectiveError, match="Unknown type"):
        dashboard.apply({"schemas": {"existing": VALID_SCHEMA, "quotes": INVALID_SCHEMA}})

    assert dashboard.state.tables == ["existing"]
    assert dashboard.tables.names() == ["existing"]

    dashboard.apply({"schemas": {"quotes": VALID_SCHEMA}, "updates": {"existing": [{"price": 99.0}], "quotes": [{"price": 101.25}]}})
    assert dashboard.state.tables == ["existing", "quotes"]
    assert dashboard.state.rows == "2"
