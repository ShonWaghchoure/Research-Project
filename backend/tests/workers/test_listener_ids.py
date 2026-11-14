"""Bug fix: every event in a multi-event transaction gets its own audit row id."""

from app.workers.listener import _event_resource_id


def test_events_in_one_batch_tx_have_distinct_ids():
    tx = "0x" + "ab" * 32
    ids = {_event_resource_id("TradeSettled", tx, i) for i in range(10)}
    assert len(ids) == 10
    assert all(len(i) <= 64 for i in ids)
