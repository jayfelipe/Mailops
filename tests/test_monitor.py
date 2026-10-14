from mailops import monitor


def test_dead_letter_flags():
    assert monitor.conditions(queued=0, failed=1, oldest_queued_s=0) == ["dead_letter"]


def test_stuck_queue_flags():
    assert monitor.conditions(queued=3, failed=0, oldest_queued_s=600) == ["queue_stuck"]


def test_fresh_queue_is_quiet():
    assert monitor.conditions(queued=5, failed=0, oldest_queued_s=60) == []


def test_empty_queue_is_quiet():
    assert monitor.conditions(queued=0, failed=0, oldest_queued_s=0) == []