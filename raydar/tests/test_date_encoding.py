import time
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from raydar.dashboard import Dashboard
from raydar.dashboard.dashboard import TableHost, _to_epoch_millis

DATES = [date(2026, 8, 21), date(2024, 2, 29), date(1969, 12, 31)]


@pytest.fixture(params=["UTC0", "UTC-8", "UTC+5"] if hasattr(time, "tzset") else [None])
def local_timezone(request, monkeypatch):
    if request.param is None:
        yield
        return
    try:
        with monkeypatch.context() as patch:
            patch.setenv("TZ", request.param)
            time.tzset()
            yield
    finally:
        time.tzset()


def utc_millis(day):
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


@pytest.mark.parametrize("day", DATES)
def test_date_encodes_at_utc_midnight(day, local_timezone):
    assert _to_epoch_millis(day) == utc_millis(day)


def test_table_host_preserves_calendar_dates(local_timezone):
    host = TableHost()
    host.new_table("dates", {"day": "date", "value": "integer"})
    rows = [{"day": day, "value": index} for index, day in enumerate(DATES)]

    host.update("dates", rows)

    view = host._tables["dates"].view()
    try:
        stored = view.to_columns()
    finally:
        view.delete()
    assert stored["day"] == [utc_millis(day) for day in DATES]
    assert stored["value"] == [0, 1, 2]
    assert [row["day"] for row in rows] == DATES


def test_dashboard_apply_preserves_calendar_date(local_timezone):
    dashboard = Dashboard()
    dashboard.apply({"schemas": {"dates": {"day": "date"}}, "updates": {"dates": [{"day": DATES[0]}]}})

    view = dashboard.tables._tables["dates"].view()
    try:
        assert view.to_columns()["day"] == [utc_millis(DATES[0])]
    finally:
        view.delete()
    assert dashboard.state.rows == "1"


@pytest.mark.parametrize("tz", [UTC, timezone(timedelta(hours=5, minutes=30))])
def test_aware_datetime_keeps_its_instant(tz):
    moment = datetime(2026, 8, 21, 12, 30, tzinfo=tz)
    assert _to_epoch_millis(moment) == int(moment.timestamp() * 1000)


def test_naive_datetime_keeps_existing_local_time_semantics():
    moment = datetime(2026, 8, 21, 12, 30)
    assert _to_epoch_millis(moment) == int(moment.timestamp() * 1000)


@pytest.mark.parametrize("value", [None, 0, "2026-08-21"])
def test_other_values_are_unchanged(value):
    assert _to_epoch_millis(value) == value
